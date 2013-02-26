-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA1

{
 "updated": "2013-01-10 12.04:29-05:00", 
 "iqn": "iqn.2012-12.com.example.foovendor:released:pinky:server:amd64:ec2:us-east-1:stream", 
 "description": "Foovendor released Cloud Images for amd64 in ec2 us-east-1", 
 "tags": {
  "endpoint": "https://ec2.us-east-1.amazonaws.com", 
  "stream": "released", 
  "region": "us-east-1", 
  "version": "12.04", 
  "build": "server", 
  "release": "precise", 
  "arch": "amd64", 
  "cloud": "aws"
 }, 
 "item_groups": [
  {
   "items": [
    {
     "root_store": "instance-store", 
     "virt_type": "paravirtual", 
     "name": "foovendor-pinky-12.04-amd64-server-20121026.1", 
     "image_id": "ami-1f24a976"
    }, 
    {
     "root_store": "ebs", 
     "virt_type": "paravirtual", 
     "name": "ebs/foovendor-pinky-12.04-amd64-server-20121026.1", 
     "image_id": "ami-e720ad8e"
    }
   ], 
   "serial": 20121026.1, 
   "label": "release"
  }, 
  {
   "items": [
    {
     "root_store": "instance-store", 
     "virt_type": "paravirtual", 
     "name": "foovendor-pinky-12.04-amd64-server-20121001", 
     "image_id": "ami-52863e3b"
    }, 
    {
     "root_store": "ebs", 
     "virt_type": "paravirtual", 
     "name": "ebs/foovendor-pinky-12.04-amd64-server-20121001", 
     "image_id": "ami-9878c0f1"
    }
   ], 
   "serial": 20121001, 
   "label": "release"
  }, 
  {
   "items": [
    {
     "root_store": "instance-store", 
     "virt_type": "paravirtual", 
     "name": "foovendor-pinky-12.04-amd64-server-20120929", 
     "image_id": "ami-cd4cf1a4"
    }, 
    {
     "root_store": "ebs", 
     "virt_type": "paravirtual", 
     "name": "ebs/foovendor-pinky-12.04-amd64-server-20120929", 
     "image_id": "ami-3b4ff252"
    }
   ], 
   "serial": 20120929, 
   "label": "beta2"
  }
 ], 
 "format": "stream:1.0"
}
-----BEGIN PGP SIGNATURE-----
Version: GnuPG v1.4.12 (GNU/Linux)

iJwEAQECAAYFAlEsQiUACgkQqXFKIDlnU261cQQAs6JJL1Je8iY1GZ36TONYRokz
tb5GTn93GXayofDcSokvIrRpV8O+UrQG2FrMYn9Vn5+0LKhNkKJP3Fh8p5bZy5Pd
UrxIFW8+U52qybg3b10U9uqvKhix8G7tYNcw6171DxKzdDTM3970rYcC85GFiHJJ
OvVx6l2J5DgcF7p/xZU=
=MBnd
-----END PGP SIGNATURE-----
