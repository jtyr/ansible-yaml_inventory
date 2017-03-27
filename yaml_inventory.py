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
import sys
import yaml


# Get logger
log = logging.getLogger(__name__)


def create_symlinks(vars_path, group_vars_path):
    for root, dirs, files in os.walk(vars_path):
        for f in files:
            src = "%s/%s" % (root, f)
            src_list = src[len(vars_path)+1:].split('/')

            # Keep only the top-level "all" file
            if src_list[-1] == 'all' and len(src_list) > 1:
                del src_list[-1]

            dst = "%s/%s" % (group_vars_path, '-'.join(src_list))

            # Make the source relative to the destination
            src = os.path.relpath(src, os.path.dirname(dst))

            # Clear files and dirs of the same name
            try:
                if os.path.isdir(dst):
                    os.rmdir(dst)
                elif os.path.exists(dst) or os.path.lexists(dst):
                    os.remove(dst)
            except Exception as e:
                log.error("E: Cannot delete %s.\n%s" % (dst, e))
                sys.exit(1)

            # Create new symlink
            try:
                os.symlink(src, dst)
            except Exception as e:
                log.error("E: Cannot create symlink.\n%s" % e)
                sys.exit(1)


def walk_yaml(inv, data, path=[], level=0):
    if data is None:
        return

    # Create vars for the "all" group if defined
    if level == 0 and ':vars' in data:
        inv['all'] = {
            'vars': data[':vars']
        }

    for gk, gv in dict((k, v) for k, v in data.items() if k[0] != ':').items():
        gpath = path + [gk]
        group = '-'.join(gpath)

        # Create vault group and make the real group as its child
        if len(path):
            inv["%s.vault" % group] = {
                'children': [
                    group
                ],
                'hosts': []
            }

        # Initiate te group
        inv[group] = {
            'hosts': []
        }

        # Walk through internal keys if any
        if gv is not None:
            for k, v in gv.items():
                if k[0] == ':':
                    # Non-group
                    if k == ':hosts':
                        for h in v:
                            # Distinguish between list and str
                            if isinstance(h, dict):
                                inv[group]['hosts'].append(list(h.keys())[0])
                                inv['_meta']['hostvars'].update(h)
                            else:
                                inv[group]['hosts'].append(h)
                    elif k == ':vars':
                        inv[group]['vars'] = v
                    elif k == ':groups' and isinstance(v, list):
                        for g in v:
                            if g not in inv:
                                inv[g] = {
                                    'hosts': []
                                }
                else:
                    # Another subgroup
                    if 'children' not in inv[group]:
                        inv[group]['children'] = []

                    inv[group]['children'].append('%s-%s.vault' % (group, k))
            else:
                # Add group hosts into the linked groups
                if ':groups' in gv:
                    for g in gv[':groups']:
                        for h in inv[group]['hosts']:
                            if h not in inv[g]['hosts']:
                                inv[g]['hosts'].append(h)

            # Walk the subgroup
            walk_yaml(inv, gv, gpath, level+1)


def read_yaml_file(f_path):
    content = ''

    try:
        f = open(f_path, 'r')
    except IOError as e:
        log.error("E: Cannot open file %s.\n%s" % (f_path, e))
        sys.exit(1)

    for line in f.readlines():
        if not line.startswith('---'):
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
    if 'YAML_INVENTORY_CREATE_SYMLINKS' in os.environ:
        symlinks = os.environ['YAML_INVENTORY_CREATE_SYMLINKS']

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
      '    location of the config file (possible locations:\n'
      '      ./yaml_inventory.conf\n'
      '      ~/.ansible/yaml_inventory.conf\n'
      '      /etc/ansible/yaml_inventory.conf)\n'
      '  YAML_INVENTORY_PATH\n'
      '    location of the inventory directory (./ by default)\n'
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
                k[0] != ':vars')))

    # Create group_vars symlinks if enabled
    if symlinks:
        create_symlinks(vars_path, group_vars_path)

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
