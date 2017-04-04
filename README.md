yaml_inventory
==============

Ansible dynamic inventory reading the inventory from YAML file.


Description
-----------

Standard Ansible inventory file has a flat structure where all groups are
on the same level and relate to each other via `:children` definition.
This leads to long group names when trying to capture more complex
relationships. Inventory groups also correspond to `group_vars` files
which are also affected by the complexity of the group names.

This Ansible dynamic inventory script is trying to address these issues
by reading the inventory from YAML file. The YAML hierarchical format
significantly simplifies the way how the groups are named and how the
relationship between the groups are created. It also allows to insert
hosts into multiple groups (e.g. groups with common configuration)
without the need to define the hosts again which reduces the data
redundancy in the inventory file.

The script also simplifies the use of Vault files by automatically
creating relationship between the group (e.g. `mygroup`) and the secured
content of that group (`mygroup.vault`). This convention makes sure that
the Vault `group_vars` file is always loaded if it exists.

For comparison, here is the standard inventory file allowing the
features mentioned above:

```
[aws:children]
aws-dev
aws-qa
aws-stg
aws-prd

[aws-dev]
aws-dev-host01          ansible_host=192.168.1.15

[aws-dev:children]
aws-dev-jenkins.vault

[aws-dev-jenkins.vault:children]
aws-dev-jenkins

[aws-dev-jenkins]
aws-dev-jenkins01       ansible_host=192.168.1.16

[aws-qa]
aws-qa-host01           ansible_host=192.168.2.15

[aws-stg]
aws-stg-host01          ansible_host=192.168.3.15

[aws-prd]
aws-prd-host01          ansible_host=192.168.4.15


[azure:children]
azure-dev
azure-qa
azure-stg
azure-prd

[azure-dev]
azure-dev-host01        ansible_host=10.0.1.15

[azure-dev:children]
azure-dev-jenkins.vault

[azure-dev-jenkins.vault:children]
azure-dev-jenkins

[azure-dev-jenkins]
azure-dev-jenkins01     ansible_host=10.0.1.16

[azure-qa]
azure-qa-host01         ansible_host=10.0.2.15

[azure-stg]
azure-stg-host01        ansible_host=10.0.3.15

[azure-prd]
azure-prd-host01        ansible_host=10.0.4.15


[template-dmz]
aws-dev-jenkins01       ansible_host=192.168.1.16
azure-dev-jenkins01     ansible_host=10.0.1.16
```

And here is how the same looks in YAML:

```
---

aws:
  dev:
    :hosts:
      - aws-dev-host01:        { ansible_host: 192.168.1.15 }
    jenkins:
      :hosts:
        - aws-dev-jenkins01:   { ansible_host: 192.168.1.16 }
      :groups:
        - template_dmz
  qa:
    :hosts:
      - aws-qa-host01:         { ansible_host: 192.168.2.15 }
  stg:
    :hosts:
      - aws-stg-host01:        { ansible_host: 192.168.3.15 }
  prd:
    :hosts:
      - aws-prd-host01:        { ansible_host: 192.168.4.15 }

azure:
  dev:
    :hosts:
      - azure-dev-host01:      { ansible_host: 10.0.1.15 }
    jenkins:
      :hosts:
        - azure-dev-jenkins01: { ansible_host: 10.0.1.16 }
      :groups:
        - template_dmz
  qa:
    :hosts:
      - azure-qa-host01:       { ansible_host: 10.0.2.15 }
  stg:
    :hosts:
      - azure-stg-host01:      { ansible_host: 10.0.3.15 }
  prd:
    :hosts:
      - azure-prd-host01:      { ansible_host: 10.0.4.15 }
```


Usage
-----

### Inventory YAML file

The main YAML inventory should be stored in the `main.yaml` file located
by default in the `inventory` directory. The location can be changed in
the config file (`inventory_path`) or via environment variable
(`YAML_INVENTORY_PATH`).

This is an example of a monolithic inventory YAML file:

```
---

aws:
  dev:
    elk:
      elasticsearch:
        # Hosts of the aws-dev-elk-elasticsearch group
        :hosts:
          - elk01: { ansible_host: 192.168.1.11 }
          - elk02: { ansible_host: 192.168.1.12 }
          - elk03: { ansible_host: 192.168.1.13 }
        # Vars for the aws-dev-elk-elasticsearch group
        :vars:
          ansible_user: ansible
      kibana:
        :hosts:
          - elk04:
              ansible_host: 192.168.1.14
    pulp:
      :hosts:
        - pulp01
      :groups:
        # List of additional groups where the hosts will be added
        - template-pulp
  qa:
  stg:
  prd:
```

The same like above but with YAML reference:

```
---

# This is a subset of the main data structure referenced bellow
aws-dev: &aws-dev
  elk:
    elasticsearch:
      # Hosts of the aws-dev-elk-elasticsearch group
      :hosts:
        - elk01: { ansible_host: 192.168.1.11 }
        - elk02: { ansible_host: 192.168.1.12 }
        - elk03: { ansible_host: 192.168.1.13 }
      # Vars for the aws-dev-elk-elasticsearch group
      :vars:
        ansible_user: ansible
    kibana:
      :hosts:
        - elk04:
            ansible_host: 192.168.1.14
  pulp:
    :hosts:
      - pulp01
    :groups:
      # List of additional groups where the hosts will be added
      - template-pulp

# This is the main data structure
aws:
  dev:
    # Reference to the above data structure
    <<: *aws-dev
  qa:
  stg:
  prd:
```

This is the same like above but with the referenced content in a separate
file:

Content of the `aws-dev.yaml` file:

```
---

# This can be still referenced from the main YAML file
aws-dev: &aws-dev
  elk:
    elasticsearch:
      # Hosts of the aws-dev-elk-elasticsearch group
      :hosts:
        - elk01: { ansible_host: 192.168.1.11 }
        - elk02: { ansible_host: 192.168.1.12 }
        - elk03: { ansible_host: 192.168.1.13 }
      # Vars for the aws-dev-elk-elasticsearch group
      :vars:
        ansible_user: ansible
    kibana:
      :hosts:
        - elk04:
            ansible_host: 192.168.1.14
  pulp:
    :hosts:
      - pulp01
    :groups:
      # List of additional groups where the hosts will be added
      - template-pulp
```

Content of the `main.yaml` file:

```
---

# This is the main data structure
aws:
  dev:
    # Refference the above data structure
    <<: *aws-dev
  qa:
  stg:
  prd:
```

The inventory script reads all YAML files from the `inventory` directory
and merges them all together. The `main.yaml` portion is always inserted
at the end so that the YAML references can still be resolved. Group names
are composed from elements of the tree separated by `-` sign.


### Inventory vars

Classical `group_vars` files can be structured in two levels only - files
in the `group_vars` directory and file in the directories located in the
`group_vars` directory. This is quite restrictive and forces the user to
capture the inventory groups structure in the `group_vars` file name.

This Ansible dynamic inventory is trying to address this issue by
introducing the inventory vars. Inventory vars are variation of the
`group_vars` with the difference that it copies the hierarchical
structure of YAML inventory file. The inventory vars directory is by
default in the `inventory/vars` directory but can be changed in the
config file (`inventory_vars_path`) or via environment variable
(`YAML_INVENTORY_VARS_PATH`). This feature is enabled by default but can
be disabled by setting the `create_symlinks` config option or the
`YAML_INVENTORY_CREATE_SYMLINKS` environment variable to value `no`.

The inventory vars file for a specific group can be called either like
the last element of the group name or like `all` inside a directory
called like the last element of the group name. If the group contains
another groups, only the second option is available because there cannot
coexist file and directory of the same name.

If this is the inventory file:

```
---

# This is a group containing another group (vars in `all` file)
aws:
  dev:
    # This is the leaf group (vars in `jenkins` file)
    jenkins:
      :hosts:
        - aws-dev-jenkins01
```

then this is the corresponding file structure of the inventory vars:

```
$ tree -p inventory
inventory
└── [drwxr-xr-x]  aws
    ├── [-rw-r--r--]  all
    └── [drwxr-xr-x]  dev
        └── [-rw-r--r--]  jenkins
```

The inventory vars are symlinked into the `group_vars` directory during
the execution of the inventory script. The `group_vars` file names are
based on the structure of the invetory vars directory. From the example
above, the path `invenotory/aws/all` is symlinked like `group_vars/aws`
and the path `invenotory/aws/dev/jenkins` is simliked like
`group_vars/aws-dev-jenkins`.

```
$ ls -la ./group_vars
total 8
drwxr-xr-x 2 jtyr users 4096 Mar 28 17:20 .
drwxr-xr-x 9 jtyr users 4096 Mar 27 10:10 ..
lrwxrwxrwx 1 jtyr users   21 Mar 28 17:20 aws -> ../inventory/vars/aws/all
lrwxrwxrwx 1 jtyr users   29 Mar 28 17:20 aws-dev-jenkins -> ../inventory/vars/aws/dev/jenkins
```


### Inventory script

The inventory script can be used as any other Ansible dynamic inventory.
With the default settings (the `main.yaml` inventory file in the
`./inventory` directory and the inventory files in the `./inventory/vars`
directory) the command can be as follows:

```
$ ansible-playbook -i ./yaml_inventory.py site.yaml
```

The inventory script implements the standard `--list` and `--host`
command line options and can be influenced by a config file (see
`yaml_inventory.conf` file) or environment variables:

```
usage: yaml_inventory.py [-h] [--list] [--host HOST]

Ansible dynamic inventory reading YAML file.

optional arguments:
  -h, --help   show this help message and exit
  --list       list all groups and hosts
  --host HOST  get vars for a specific host

environment variables:
  YAML_INVENTORY_CONFIG_PATH
    location of the config file (possible locations:
      ./yaml_inventory.conf
      ~/.ansible/yaml_inventory.conf
      /etc/ansible/yaml_inventory.conf)
  YAML_INVENTORY_PATH
    location of the inventory directory (./inventory by default)
  YAML_INVENTORY_VARS_PATH
    location of the inventory vars directory (YAML_INVENTORY_PATH/vars by default)
  YAML_INVENTORY_GROUP_VARS_PATH
    location of the vars directory (./group_vars by default)
  YAML_INVENTORY_CREATE_SYMLINKS
    flag to create group_vars symlinks (enabled by default)
```


TODO
----

- Implement hosts enumeration.
- Implement adding hosts from an other group via regexp.


License
-------

MIT


Author
------

Jiri Tyr
