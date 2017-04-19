#!/usr/bin/env python

try:
    import ConfigParser as configparser
except:
    import configparser

import argparse
import glob
import json
import logging
import os
import re
import sys
import yaml


# Get logger
log = logging.getLogger(__name__)


def create_symlinks(vars_path, group_vars_path, inv):
    for root, dirs, files in os.walk(vars_path):
        for f in files:
            src = "%s/%s" % (root, f)
            src_list = src[len(vars_path)+1:].split('/')

            # Ignore dotted (e.g. ".git")
            if src_list[0].startswith('.'):
                continue

            # Strip out the YAML file extension
            if src_list[-1].endswith('.yaml'):
                src_list[-1] = src_list[-1][:-5]
            elif src_list[-1].endswith('.yml'):
                src_list[-1] = src_list[-1][:-4]
            elif src_list[-1].endswith('.yaml.vault'):
                src_list[-1] = "%s.vault" % src_list[-1][:-11]
            elif src_list[-1].endswith('.yml.vault'):
                src_list[-1] = "%s.vault" % src_list[-1][:-10]

            # Keep only the top-level "all" file
            if src_list[-1] in ['all', 'all.vault'] and len(src_list) > 1:
                # Keep the .vault extension
                if src_list[-1] == 'all.vault':
                    src_list[-2] += '.vault'

                del src_list[-1]

            src_list_s = '-'.join(src_list)
            dst = []

            # Ignore files which are not groups
            if src_list[0] in ['all', 'all.vault'] or src_list_s in inv.keys():
                dst.append("%s/%s" % (group_vars_path, src_list_s))

            # Add templates into the dst list
            for ig in inv.keys():
                if '@' in ig:
                    g, t = ig.split('@')

                    if t == src_list_s:
                        dst.append("%s/%s" % (group_vars_path, ig))

            # Create all destination symlinks
            for d in dst:
                # Make the source relative to the destination
                s = os.path.relpath(src, os.path.dirname(d))

                # Clear files and dirs of the same name
                try:
                    if os.path.isdir(d):
                        os.rmdir(d)
                    elif os.path.exists(d) or os.path.lexists(d):
                        os.remove(d)
                except Exception as e:
                    log.error("E: Cannot delete %s.\n%s" % (d, e))
                    sys.exit(1)

                # Create new symlink
                try:
                    os.symlink(s, d)
                except Exception as e:
                    log.error("E: Cannot create symlink.\n%s" % e)
                    sys.exit(1)


def read_vars_file(inv, group, vars_path, symlinks, vars_always=False):
    g = group

    # Get template name
    if '@' in group:
        _, g = group.split('@')

    # Do not try to load vault files
    if g.endswith('.vault'):
        return

    path = "%s/%s" % (vars_path, g.replace('-', '/'))
    data = None

    # Check if vars file exists
    if os.path.isfile(path):
        pass
    elif os.path.isfile("%s/all" % path):
        path += '/all'
    else:
        path = None

    # Read the group file or the "all" file from the group dir if exists
    if path is not None:
        try:
            data = yaml.load(read_yaml_file(path, False))
        except yaml.YAMLError as e:
            log.error("E: Cannot load YAML inventory vars file.\n%s" % e)
            sys.exit(1)

    # Create empty group if needed
    if group not in inv:
        inv[group] = {
            'hosts': []
        }

    # Create empty vars if required
    if (
            (
                vars_always or
                (
                    data is not None and
                    not symlinks)) and
            'vars' not in inv[group]):
        inv[group]['vars'] = {}

    # Update the vars with the file data if any
    if data is not None and not symlinks:
        inv[group]['vars'].update(data)


def add_param(inv, path, param, val, vars_path, symlinks):
    if param.startswith(':'):
        param = param[1:]

    _path = list(path)

    if symlinks:
        # Create link g1.vault -> g1
        _path[-1] += '.vault'
        add_param(inv, _path, 'children', ['-'.join(path)], vars_path, False)

        if isinstance(val, list) and len(val) and param == 'children':
            val[0] += '.vault'

    group = '-'.join(path)

    # Add empty group
    if group not in inv:
        inv[group] = {}

    # Add empty parameter
    if param not in inv[group]:
        if param == 'vars':
            inv[group][param] = {}
        else:
            inv[group][param] = []

    # Add parameter value
    if isinstance(inv[group][param], dict) and isinstance(val, dict):
        inv[group][param].update(val)
    elif isinstance(inv[group][param], list) and isinstance(val, list):
        # Add individual items if they don't exist
        for v in val:
            if v not in inv[group][param]:
                inv[group][param] += val

    # Read inventory vars file
    if not symlinks:
        read_vars_file(inv, group, vars_path, symlinks)


def walk_yaml(inv, data, vars_path, symlinks, parent=None, path=[]):
    if data is None:
        return

    params = list(k for k in data.keys() if k[0] == ':')
    groups = list(k for k in data.keys() if k[0] != ':')

    for p in params:
        if parent is None:
            _path = ['all']
        else:
            _path = list(path)

        if p == ':templates' and parent is not None:
            for t in data[p]:
                _pth = list(_path)
                _pth[-1] += "@%s" % t

                add_param(
                    inv, _pth, 'children', ['-'.join(_path)], vars_path,
                    symlinks)

        elif p == ':hosts':
            for h in data[p]:
                # Add host with vars into the _meta hostvars
                if isinstance(h, dict):
                    if list(h.keys())[0] not in inv['_meta']['hostvars']:
                        inv['_meta']['hostvars'].update(h)

                    add_param(
                        inv, _path, p, [list(h.keys())[0]], vars_path,
                        symlinks)
                else:
                    add_param(inv, _path, p, [h], vars_path, symlinks)

        elif p == ':vars':
            add_param(inv, _path, p, data[p], vars_path, symlinks)

        elif p == ':groups' and ':hosts' in data:
            for g in data[p]:
                g_path = g.split('-')

                # Add hosts in the same way like above
                for h in data[':hosts']:
                    if isinstance(h, dict):
                        add_param(
                            inv, g_path, 'hosts', [list(h.keys())[0]],
                            vars_path, symlinks)
                    else:
                        add_param(
                            inv, g_path, 'hosts', [h], vars_path, symlinks)

        elif p == ':add_hosts':
            key = '__YAML_INVENTORY'

            if key not in inv:
                inv[key] = []

            record = {
                'path': path,
                'patterns': data[p]
            }

            # Make a list of groups which want to add hosts by regexps
            inv[key].append(record)

    for g in groups:
        if parent is not None:
            if data[g] is not None and ':templates' in data[g]:
                for t in data[g][':templates']:
                    _path = list(path + [g])
                    _path[-1] += "@%s" % t

                    add_param(
                        inv, path, 'children', ['-'.join(_path)], vars_path,
                        symlinks)

            add_param(
                inv, path, 'children', ['-'.join(path + [g])], vars_path,
                symlinks)

        walk_yaml(inv, data[g], vars_path, symlinks, g, path + [g])


def read_yaml_file(f_path, strip_hyphens=True):
    content = ''

    try:
        f = open(f_path, 'r')
    except IOError as e:
        log.error("E: Cannot open file %s.\n%s" % (f_path, e))
        sys.exit(1)

    for line in f.readlines():
        if not strip_hyphens or strip_hyphens and not line.startswith('---'):
            content += line

    try:
        f.close()
    except IOError as e:
        log.error("E: Cannot close file %s.\n%s" % (f_path, e))
        sys.exit(1)

    return content


def read_inventory(inventory_path):
    # Check if the path is a directory
    if not os.path.isdir(inventory_path):
        log.error(
            "E: No inventory directory %s.\n"
            "Use YAML_INVENTORY_PATH environment variable to specify the "
            "custom directory." % inventory_path)
        sys.exit(1)

    if not (
            os.path.isfile("%s/main.yaml" % inventory_path) or
            os.path.isfile("%s/main.yml" % inventory_path)):
        log.error(
            "E: Cannot find %s/main.yaml." % inventory_path)
        sys.exit(1)

    # Get names of all YAML files
    yaml_files = glob.glob("%s/*.yaml" % inventory_path)
    yaml_files += glob.glob("%s/*.yml" % inventory_path)

    yaml_main = ''
    yaml_content = ''

    # Read content of all the files
    for f_path in sorted(yaml_files):
        file_name = os.path.basename(f_path)

        # Keep content of the main.yaml file in a separate variable
        if file_name == 'main.yaml' or file_name == 'main.yml':
            yaml_main += read_yaml_file(f_path)
        else:
            yaml_content += read_yaml_file(f_path)

    # Convert YAML string to data structure
    try:
        data = yaml.load(yaml_content + yaml_main)
        data_main = yaml.load(yaml_main.replace(' *', ''))
    except yaml.YAMLError as e:
        log.error("E: Cannot load YAML inventory.\n%s" % e)
        sys.exit(1)

    if data is not None:
        # Delete all non-main variables
        for key in list(data.keys()):
            if key not in data_main:
                data.pop(key, None)

    return data, data_main


def get_vars(config):
    cwd = os.getcwd()
    inventory_path = "%s/inventory" % cwd

    # Check if there is the config var specifying the inventory dir
    if config.has_option('paths', 'inventory_path'):
        inventory_path = config.get('paths', 'inventory_path')

    # Check if there is the env var specifying the inventory dir
    if 'YAML_INVENTORY_PATH' in os.environ:
        inventory_path = os.environ['YAML_INVENTORY_PATH']

    vars_path = "%s/vars" % inventory_path

    # Check if there is the config var specifying the inventory/vars dir
    if config.has_option('paths', 'inventory_vars_path'):
        vars_path = config.get('paths', 'inventory_vars_path')

    # Check if there is the env var specifying the inventory/vars dir
    if 'YAML_INVENTORY_VARS_PATH' in os.environ:
        vars_path = os.environ['YAML_INVENTORY_VARS_PATH']

    group_vars_path = "%s/group_vars" % cwd

    # Check if there is the config var specifying the group_vars dir
    if config.has_option('paths', 'group_vars_path'):
        group_vars_path = config.get('paths', 'group_vars_path')

    # Check if there is the env var specifying the group_vars dir
    if 'YAML_INVENTORY_GROUP_VARS_PATH' in os.environ:
        group_vars_path = os.environ['YAML_INVENTORY_GROUP_VARS_PATH']

    symlinks = True

    # Check if there is the config var specifying the create_symlinks flag
    if config.has_option('features', 'create_symlinks'):
        try:
            symlinks = config.getboolean('features', 'create_symlinks')
        except ValueError as e:
            log.error("E: Wrong value of the create_symlinks option.\n%s" % e)

    # Check if there is the env var specifying the create_symlinks flag
    if (
            'YAML_INVENTORY_CREATE_SYMLINKS' in os.environ and
            os.environ['YAML_INVENTORY_CREATE_SYMLINKS'].lower() not in [
                '1', 'yes', 'y', 'true']):
        symlinks = False

    return inventory_path, vars_path, group_vars_path, symlinks


def read_config():
    # Possible config file locations
    config_locations = [
        'yaml_inventory.conf',
        os.path.expanduser('~/.ansible/yaml_inventory.conf'),
        '/etc/ansible/yaml_inventory.conf'
    ]

    # Add the env var into the list if defined
    if 'YAML_INVENTORY_CONFIG_PATH' in os.environ:
        config_locations = (
            [os.environ['YAML_INVENTORY_CONFIG_PATH']] + config_locations)

    config = configparser.ConfigParser()

    # Search for the config file and read it if found
    for cl in config_locations:
        if os.path.isfile(cl):
            try:
                config.read(cl)
            except Exception as e:
                log.error('E: Cannot read config file %s.\n%s', (cl, e))
                sys.exit(1)

            break

    return config


def parse_arguments():
    description = 'Ansible dynamic inventory reading YAML file.'
    epilog = (
      'environment variables:\n'
      '  YAML_INVENTORY_CONFIG_PATH\n'
      '    location of the config file (default locations:\n'
      '      ./yaml_inventory.conf\n'
      '      ~/.ansible/yaml_inventory.conf\n'
      '      /etc/ansible/yaml_inventory.conf)\n'
      '  YAML_INVENTORY_PATH\n'
      '    location of the inventory directory (./inventory by default)\n'
      '  YAML_INVENTORY_VARS_PATH\n'
      '    location of the inventory vars directory (YAML_INVENTORY_PATH/vars '
      'by default)\n'
      '  YAML_INVENTORY_GROUP_VARS_PATH\n'
      '    location of the vars directory (./group_vars by default)\n'
      '  YAML_INVENTORY_CREATE_SYMLINKS\n'
      '    flag to create group_vars symlinks (enabled by default)')

    parser = argparse.ArgumentParser(
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--list',
        action='store_true',
        help='list all groups and hosts')
    parser.add_argument(
        '--host',
        metavar='HOST',
        help='get vars for a specific host')

    return (parser.parse_args(), parser)


def main():
    # Configure the logger (required for Python v2.6)
    logging.basicConfig()

    # Parse command line arguments
    (args, parser) = parse_arguments()

    if not args.list and args.host is None:
        log.error('No action specified.')
        parser.print_help()
        sys.exit(1)

    # Read config file
    config = read_config()

    # Get config vars
    (inventory_path, vars_path, group_vars_path, symlinks) = get_vars(config)

    # Read the inventory
    (data, data_main) = read_inventory(inventory_path)

    # Initiate the dynamic inventory
    dyn_inv = {
        '_meta': {
            'hostvars': {}
        }
    }

    # Walk through the data structure (start with groups only)
    if data is not None:
        walk_yaml(
            dyn_inv,
            dict((k, v) for k, v in data.items() if (
                k[0] != ':' or
                k[0] != ':vars')),
            vars_path,
            symlinks)

    # Add hosts by regexp
    if '__YAML_INVENTORY' in dyn_inv:
        tmp_inv = dict(dyn_inv)

        for inv_group, inv_group_content in tmp_inv.items():
            if (
                    not inv_group.endswith('.vault') and
                    '@' not in inv_group and
                    'hosts' in inv_group_content):
                for re_data in tmp_inv['__YAML_INVENTORY']:
                    for pattern in re_data['patterns']:
                        for host in inv_group_content['hosts']:
                            if re.match(pattern, host):
                                add_param(
                                    dyn_inv, re_data['path'], 'hosts', [host],
                                    vars_path, symlinks)

        # Clear the regexp data
        tmp_inv = None
        dyn_inv.pop('__YAML_INVENTORY', None)

    # Create group_vars symlinks if enabled
    if symlinks:
        create_symlinks(vars_path, group_vars_path, dyn_inv)

    # Get the host's vars if requested
    if args.host is not None:
        if args.host in dyn_inv['_meta']['hostvars']:
            dyn_inv = dyn_inv['_meta']['hostvars'][args.host]
        else:
            dyn_inv = {}

    # Print the final dynamic inventory in JSON format
    print(json.dumps(dyn_inv, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
