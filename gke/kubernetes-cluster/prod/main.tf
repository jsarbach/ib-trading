terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "4.8.0"
    }
  }
}

variable "project_id" {
    type = string
    default = "api-project-786272790820" 
}
variable "region" {
    type = string
    default = "europe-southwest1" 

}
variable "zone" {
    type = string
    default = "europe-southwest1-a" 

}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

resource "google_compute_network" "ib_trading_net" {
  provider = google-beta
  project = var.project_id
  name = "ib-trading-net"
  auto_create_subnetworks = false
}

#tfimport-terraform import google_compute_subnetwork.ib_trading_subnet __project__/europe-southwest1/ib-trading-subnet
resource "google_compute_subnetwork" "ib_trading_subnet" {
  provider = google-beta

  name = "ib-trading-subnet"
  ip_cidr_range = "10.172.0.0/20"
  project      = var.project_id
  region       = var.region
  # zone         = var.zone
  private_ip_google_access = true
  network = google_compute_network.ib_trading_net.id
}

#tfimport-terraform import google_compute_firewall.ib_trading_net_allow_internal  __project__/ib-trading-net-allow-internal
resource "google_compute_firewall" "ib_trading_net_allow_internal" {
  provider = google-beta

  name = "ib-trading-net-allow-internal"
  direction = "INGRESS"
  project      = var.project_id
  priority = 1000
  source_ranges = [
    "10.172.0.0/20"
  ]
  network = google_compute_network.ib_trading_net.id
  allow {
    protocol = "all"
  }
}

#tfimport-terraform import google_compute_firewall.ib_trading_net_allow_ssh_bastion_host  __project__/ib-trading-net-allow-ssh-bastion-host
resource "google_compute_firewall" "ib_trading_net_allow_ssh_bastion_host" {
  provider = google-beta
  project      = var.project_id
  name = "ib-trading-net-allow-ssh-bastion-host"
  direction = "INGRESS"
  priority = 1000
  source_ranges = [
    "0.0.0.0/0"
  ]
  target_tags = [
    "bastion-host"
  ]
  network = google_compute_network.ib_trading_net.id
  allow {
    protocol = "TCP"
    ports = ["22"]
  }
}

#tfimport-terraform import google_compute_router.nat_router  __project__/europe-southwest1/nat-router
resource "google_compute_router" "nat_router" {
  provider = google-beta

  name = "nat-router"
  network = google_compute_network.ib_trading_net.id
  project      = var.project_id
  region       = var.region
  # zone         = var.zone
}
resource "google_compute_router_nat" "nat_config" {
  name = "nat-config"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
  nat_ip_allocate_option = "AUTO_ONLY"
  log_config {
    enable = true
    filter = "ALL"
  }

  router = google_compute_router.nat_router.name
  project      = var.project_id
  region       = var.region


  depends_on = [
    google_compute_router.nat_router
  ]
}

#tfimport-terraform import google_container_cluster.ib_trading __project__//ib-trading
resource "google_container_cluster" "ib_trading" {
  provider = google-beta
  # zone = "europe-southwest1-a"
  project      = var.project_id
  # region       = var.region
  # zone         = var.zone
  name = "ib-trading"
  network = google_compute_network.ib_trading_net.id
  subnetwork = google_compute_subnetwork.ib_trading_subnet.id
  min_master_version = "latest"
  location = var.zone
  node_pool {
    name = "default-pool"
    initial_node_count = 1
    node_config {
      machine_type = "e2-small"
      disk_size_gb = 10
      oauth_scopes = [
        "https://www.googleapis.com/auth/compute",
        "https://www.googleapis.com/auth/devstorage.read_only",
        "https://www.googleapis.com/auth/logging.write",
        "https://www.googleapis.com/auth/monitoring"
      ]
      tags = [
        "ib-trading-node"
      ]
    }
    management {
      auto_upgrade = true
      auto_repair = true
    }
  }
  ip_allocation_policy {
  }
  master_authorized_networks_config {
  }
  private_cluster_config {
    enable_private_nodes = true
    enable_private_endpoint = true
    master_ipv4_cidr_block = "172.16.0.0/28"
  }
}

#tfimport-terraform import google_compute_instance.bastion_host  __project__/europe-southwest1-a/bastion-host
resource "google_compute_instance" "bastion_host" {
  provider = google-beta

  name = "bastion-host"
  project      = var.project_id
  # region       = var.region
  zone         = var.zone
  machine_type = "e2-small"
  tags = [
    "bastion-host"
  ]
  boot_disk {
    auto_delete = true
    initialize_params {
      size = 10
      image = "projects/debian-cloud/global/images/family/debian-11"
    }
  }
  network_interface {
    network = google_compute_network.ib_trading_net.id
    subnetwork = google_compute_subnetwork.ib_trading_subnet.id
  }
  metadata = {
    startup-script = <<-EOT
#!/bin/bash
sudo apt-get -y install kubectl git
gcloud container clusters get-credentials ib-trading --zone europe-southwest1-a --internal-ip

EOT
  }
  service_account {
    email = "786272790820-compute@developer.gserviceaccount.com"
    scopes = ["https://www.googleapis.com/auth/cloud-platform", "https://www.googleapis.com/auth/devstorage.read_only", "https://www.googleapis.com/auth/servicecontrol", "https://www.googleapis.com/auth/source.read_only"]
  }
}
