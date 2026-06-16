"""Verified Linode Terraform and CLI starting points.

The documentation specialist and the flat agent load `config_examples` so the
agent can answer "how do I set this up" with real, minimal Infrastructure-as-Code
instead of guessing provider syntax. Each entry was checked against the official
linode/linode Terraform provider docs and the Linode CLI reference.

They are starting points, not finished modules: real attribute names with
placeholder values. Confirm regions, plans, and versions with the list commands
before applying.
"""

from __future__ import annotations

from strands import tool

# resource key -> {title, terraform, cli, source, notes}
TEMPLATES: dict[str, dict[str, str]] = {
    "instance": {
        "title": "Small Linode instance (Nanode)",
        "terraform": r"""terraform {
  required_providers {
    linode = {
      source  = "linode/linode"
      version = "~> 2.0"
    }
  }
}

provider "linode" {
  # Reads token from the LINODE_TOKEN env var, or set token = "..."
}

resource "linode_instance" "web" {
  label           = "my-nanode"
  region          = "us-east"          # REPLACE_region (run: linode-cli regions list)
  type            = "g6-nanode-1"      # shared 1GB Nanode
  image           = "linode/ubuntu24.04"
  authorized_keys = ["ssh-ed25519 AAAA...REPLACE_pubkey user@host"]
  # root_pass is optional if you supply authorized_keys.
  # root_pass     = "REPLACE_strong_root_password"
}""",
        "cli": r"""linode-cli linodes create \
  --label my-nanode \
  --region us-east \
  --type g6-nanode-1 \
  --image linode/ubuntu24.04 \
  --authorized_keys "ssh-ed25519 AAAA...REPLACE_pubkey user@host"

# Useful lookups:
#   linode-cli regions list
#   linode-cli images list
#   linode-cli linodes types   (shows g6-nanode-1 and shared plans)""",
        "source": "https://registry.terraform.io/providers/linode/linode/latest/docs/resources/instance",
        "notes": "Only region and type are required. image is needed for a bootable disk, and when you set image you must also supply root_pass or authorized_keys or the apply errors. authorized_keys is a list, root_pass is a string. The CLI authenticates via `linode-cli configure`; Terraform reads LINODE_TOKEN. Confirm region and image with the list commands.",
    },
    "lke": {
        "title": "LKE Kubernetes cluster with one node pool",
        "terraform": r"""terraform {
  required_providers {
    linode = {
      source = "linode/linode"
    }
  }
}

provider "linode" {
  # token = "REPLACE_linode_api_token"  # or set LINODE_TOKEN
}

resource "linode_lke_cluster" "this" {
  label       = "my-lke-cluster"
  region      = "REPLACE_region"      # e.g. "us-mia"
  k8s_version = "REPLACE_k8s_version" # major.minor, e.g. "1.32"

  pool {
    type  = "g6-standard-2" # small shared 2-core node
    count = 3
  }
}

# Optional: pull the kubeconfig (base64-encoded) after apply
output "kubeconfig" {
  value     = linode_lke_cluster.this.kubeconfig
  sensitive = true
}""",
        "cli": r"""linode-cli lke cluster-create \
  --label my-lke-cluster \
  --region REPLACE_region \
  --k8s_version REPLACE_k8s_version \
  --node_pools.type g6-standard-2 \
  --node_pools.count 3

# Fetch kubeconfig once the cluster is ready (CLUSTER_ID from the create output):
# linode-cli lke kubeconfig-view CLUSTER_ID""",
        "source": "https://registry.terraform.io/providers/linode/linode/latest/docs/resources/lke_cluster",
        "notes": "Required: label, region, k8s_version, and at least one pool block with type and count. count is optional only when an autoscaler block is set. k8s_version is major.minor (for example \"1.32\"), not a patch version. Pick a real region (linode-cli regions list) and a current version (linode-cli lke versions list).",
    },
    "object_storage": {
        "title": "Object Storage bucket and a scoped access key",
        "terraform": r"""terraform {
  required_providers {
    linode = {
      source = "linode/linode"
    }
  }
}

provider "linode" {
  # token = var.linode_token  # or set LINODE_TOKEN
}

resource "linode_object_storage_bucket" "this" {
  label  = "REPLACE_bucket_label"
  region = "REPLACE_region" # e.g. us-mia
}

resource "linode_object_storage_key" "scoped" {
  label = "REPLACE_key_label"

  bucket_access {
    bucket_name = linode_object_storage_bucket.this.label
    region      = linode_object_storage_bucket.this.region
    permissions = "read_write" # or read_only
  }
}

output "access_key" {
  value = linode_object_storage_key.scoped.access_key
}

output "secret_key" {
  value     = linode_object_storage_key.scoped.secret_key
  sensitive = true
}""",
        "cli": r"""# 1. Create the bucket (takes --label and --region)
linode-cli object-storage buckets-create \
  --label REPLACE_bucket_label \
  --region REPLACE_region   # e.g. us-mia

# 2. Create a key scoped to that bucket only (Limited Access Key)
linode-cli object-storage keys-create \
  --label REPLACE_key_label \
  --bucket_access '[{"region": "REPLACE_region", "bucket_name": "REPLACE_bucket_label", "permissions": "read_write"}]'

# keys-create returns access_key and secret_key once. Save the secret now.""",
        "source": "https://registry.terraform.io/providers/linode/linode/latest/docs/resources/object_storage_key",
        "notes": "Bucket needs label and region (cluster is deprecated, use region). The key needs a label; bucket_access makes it a Limited Access Key scoped with bucket_name, region, and permissions (read_write or read_only). The secret_key is returned only at creation, so capture it immediately. Changing permissions forces a new key.",
    },
    "postgres": {
        "title": "Managed PostgreSQL database",
        "terraform": r"""terraform {
  required_providers {
    linode = {
      source  = "linode/linode"
      version = "~> 2.0"
    }
  }
}

provider "linode" {
  # token comes from LINODE_TOKEN env var
}

# Use linode_database_postgresql_v2. The old linode_database_postgresql is deprecated.
resource "linode_database_postgresql_v2" "rag" {
  label     = "rag-pg"
  engine_id = "postgresql/16"  # format is postgresql/<major>; check: linode-cli databases engines
  region    = "REPLACE_region" # e.g. us-east
  type      = "REPLACE_type"   # e.g. g6-dedicated-2; nanode/shared plans are 1-node only

  # Optional. Empty list blocks all access. CIDR or single IPs.
  allow_list   = ["203.0.113.4/32"]
  cluster_size = 1 # 1, 2, or 3. >1 needs a dedicated plan.
}

output "pg_host" {
  value = linode_database_postgresql_v2.rag.host_primary
}""",
        "cli": r"""# List engine IDs first to get a valid --engine value
linode-cli databases engines

# Create. The CLI/API flag is --engine (value postgresql/<ver>), not engine_id.
linode-cli databases postgresql-create \
  --label rag-pg \
  --region REPLACE_region \
  --type REPLACE_type \
  --engine postgresql/16 \
  --cluster_size 1 \
  --ssl_connection true \
  --allow_list 203.0.113.4/32

# Get connection details once status is "active"
linode-cli databases postgresql-list

# Enable pgvector for RAG. Run against the live DB, not via Terraform/CLI:
#   psql "postgresql://USER:PASS@HOST:PORT/defaultdb?sslmode=require" -c "CREATE EXTENSION vector;" """,
        "source": "https://registry.terraform.io/providers/linode/linode/latest/docs/resources/database_postgresql_v2",
        "notes": "Use linode_database_postgresql_v2; the plain linode_database_postgresql is deprecated. Required: label, engine_id (\"postgresql/16\"), region, type. Terraform calls it engine_id but the CLI/API flag is --engine. An empty allow_list blocks all traffic; cluster_size of 2 or 3 needs a dedicated plan. pgvector is supported: enable it on the running DB with CREATE EXTENSION vector. Provisioning takes several minutes before the host appears.",
    },
    "nodebalancer": {
        "title": "NodeBalancer with a Cloud Firewall",
        "terraform": r"""terraform {
  required_providers {
    linode = {
      source = "linode/linode"
    }
  }
}

provider "linode" {
  # token via LINODE_TOKEN env var
}

variable "backend_private_ip" {
  type    = string
  default = "REPLACE_192.168.x.x" # private IP of your backend Linode
}

resource "linode_nodebalancer" "web" {
  label  = "web-nb"
  region = "REPLACE_region" # e.g. us-east
}

resource "linode_nodebalancer_config" "web" {
  nodebalancer_id = linode_nodebalancer.web.id
  port            = 80
  protocol        = "http"
  algorithm       = "roundrobin"
  check           = "http"
  check_path      = "/"
}

resource "linode_nodebalancer_node" "web" {
  nodebalancer_id = linode_nodebalancer.web.id
  config_id       = linode_nodebalancer_config.web.id
  label           = "web-node-1"
  address         = "${var.backend_private_ip}:80" # private IP : backend port
}

# Cloud Firewall: only inbound rules apply to NodeBalancers.
resource "linode_firewall" "web" {
  label           = "web-nb-fw"
  inbound_policy  = "DROP"
  outbound_policy = "ACCEPT"

  inbound {
    label    = "allow-http"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "80" # matches the NodeBalancer listen port
    ipv4     = ["0.0.0.0/0"]
    ipv6     = ["::/0"]
  }

  nodebalancers = [linode_nodebalancer.web.id]
}""",
        "cli": r"""# 1. Create the NodeBalancer. Capture its id.
nb_id=$(linode-cli nodebalancers create \
  --region REPLACE_region --label web-nb \
  --text --no-headers --format id)

# 2. Create a port config. Capture the config id.
cfg_id=$(linode-cli nodebalancers config-create "$nb_id" \
  --port 80 --protocol http --algorithm roundrobin \
  --check http --check_path / \
  --text --no-headers --format id)

# 3. Add a backend node (private IP required). Positional: nodebalancer_id config_id
linode-cli nodebalancers node-create "$nb_id" "$cfg_id" \
  --label web-node-1 --address REPLACE_192.168.x.x:80

# 4. Create a Cloud Firewall. Only inbound rules apply to NodeBalancers.
fw_id=$(linode-cli firewalls create \
  --label web-nb-fw \
  --rules.inbound_policy DROP --rules.outbound_policy ACCEPT \
  --rules.inbound '[{"label":"allow-http","action":"ACCEPT","protocol":"TCP","ports":"80","addresses":{"ipv4":["0.0.0.0/0"],"ipv6":["::/0"]}}]' \
  --text --no-headers --format id)

# 5. Attach the firewall to the NodeBalancer.
linode-cli firewalls device-create "$fw_id" --id "$nb_id" --type nodebalancer""",
        "source": "https://registry.terraform.io/providers/linode/linode/latest/docs/resources/nodebalancer",
        "notes": "linode_nodebalancer needs region; the config defaults to port 80/http; the node address is a private IP in \"ip:port\" form. Attach the firewall with the nodebalancers argument. Only inbound rules apply to NodeBalancers, so the inbound port must match the config listen port. A NodeBalancer can have one enabled firewall at a time. Confirm the linode-cli flag spellings against your installed version.",
    },
    "vpc": {
        "title": "VPC with one subnet",
        "terraform": r"""terraform {
  required_providers {
    linode = {
      source = "linode/linode"
    }
  }
}

provider "linode" {
  # token via LINODE_TOKEN env var
}

resource "linode_vpc" "this" {
  label  = "example-vpc"
  region = "REPLACE_region" # e.g. us-iad
}

resource "linode_vpc_subnet" "this" {
  vpc_id = linode_vpc.this.id
  label  = "example-subnet"
  ipv4   = "10.0.0.0/24"
}""",
        "cli": r"""# Create the VPC and its subnet in one call
linode-cli vpcs create \
  --label example-vpc \
  --region REPLACE_region \
  --subnets.label example-subnet \
  --subnets.ipv4 10.0.0.0/24

# Or create the VPC, then add a subnet by VPC id:
# linode-cli vpcs create --label example-vpc --region REPLACE_region
# linode-cli vpcs subnet-create $vpcId --label example-subnet --ipv4 10.0.0.0/24""",
        "source": "https://registry.terraform.io/providers/linode/linode/latest/docs/resources/vpc_subnet",
        "notes": "linode_vpc requires label and region. linode_vpc_subnet requires vpc_id, label, and ipv4 (a CIDR). The region must support VPC. Labels are ASCII letters, digits, and dashes only.",
    },
}

# Common ways a user (or the model) might name a resource.
_ALIASES = {
    "linode": "instance", "compute": "instance", "vm": "instance", "nanode": "instance", "server": "instance",
    "kubernetes": "lke", "k8s": "lke", "cluster": "lke",
    "object storage": "object_storage", "bucket": "object_storage", "s3": "object_storage", "storage": "object_storage",
    "database": "postgres", "postgresql": "postgres", "pg": "postgres", "managed database": "postgres", "db": "postgres",
    "load balancer": "nodebalancer", "loadbalancer": "nodebalancer", "firewall": "nodebalancer", "nb": "nodebalancer",
    "network": "vpc", "subnet": "vpc",
}


def _resolve(resource: str) -> str | None:
    raw = (resource or "").strip().lower()
    key = raw.replace("-", "_").replace(" ", "_")
    if key in TEMPLATES:
        return key
    if raw in _ALIASES:
        return _ALIASES[raw]
    if raw.replace("_", " ") in _ALIASES:
        return _ALIASES[raw.replace("_", " ")]
    for k in TEMPLATES:
        if k in key or key in k:
            return k
    return None


@tool
def config_examples(resource: str) -> str:
    """Return verified Terraform and Linode CLI for an Akamai Cloud resource.

    Use this when a developer asks how to create or configure something on Akamai
    Cloud and wants the config or automation. Present the Terraform and CLI it
    returns as fenced code blocks, keep the source URL, and tell the user to
    confirm region, plan, and version values before applying.

    Args:
        resource: one of instance, lke, object_storage, postgres, nodebalancer,
            vpc. Aliases like kubernetes, bucket, database, or load balancer work.
    Returns:
        The title, the Terraform, the equivalent CLI, the source doc URL, and
        notes on required fields. If the resource is unknown, the supported list.
    """
    key = _resolve(resource)
    if key is None:
        return "No template for that resource. Supported: " + ", ".join(sorted(TEMPLATES)) + "."
    t = TEMPLATES[key]
    return (
        f"# {t['title']}\n\n"
        f"## Terraform (linode/linode provider)\n```hcl\n{t['terraform']}\n```\n\n"
        f"## Linode CLI\n```bash\n{t['cli']}\n```\n\n"
        f"Source: {t['source']}\n\n"
        f"Notes: {t['notes']}"
    )
