# Access Control List for Application Builder runtime workers
path "secret/data/tenants/+/kms" {
  capabilities = ["read"]
}

path "secret/data/tenants/+/database" {
  capabilities = ["read"]
}

path "auth/approle/login" {
  capabilities = ["create", "read"]
}

path "sys/leases/renew" {
  capabilities = ["update"]
}

path "sys/leases/revoke" {
  capabilities = ["update"]
}