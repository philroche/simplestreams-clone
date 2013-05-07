== Intro ==
This is a documentation, examples, a python library and some tools for
interacting with simple streams format.

The intent of simple streams format is to make well formated data available
about "products".

There is more documentation in doc/README.
There are examples in examples/.

== Simple Streams Getting Started ==

= Mirroring ==
To mirror one source (http or file) to a local directory, see tools/do-mirror.
For example, to mirror the 'foocloud' example content, do:
   ./tools/tenv do-mirror examples/foocloud/ my.out streams/v1/index.json

That will create a full mirror in my.out/.

   ./tools/tenv do-mirror --mirror=http://download.cirros-cloud.net/ \
       --max=1 examples/cirros/ cirros.mirror/

That will create a mirror of cirros data in cirros.mirror, with only
the latest file from each product.

= Hooks =
To use the "command hooks mirror" for invoking commands to synchronize, between
one source and another, see bin/sstream-sync.

For an example, the following runs the debug hook against the example 'foocloud'
data:
   ./tools/tenv sstream-sync --hook=hook-debug \
       --path=streams/v1/index.json examples/foocloud/

You can also run it with cloud-images.ubuntu.com data like this:

  ./tools/tenv sstream-sync \
     --item-skip-download --hook=./tools/hook-debug \
     --path=streams/v1/index.sjson http://cloud-images.ubuntu.com/releases/

The 'hook-debug' program simply outputs the data it is invoked with.  It does
not actually mirror anything.


== Glance ==
Example mirror of a download image source to glance with swift serving
a localized image-id format:

./tools/sstream-mirror-glance --region=RegionOne \
   --cloud-name=localcloud "--content-id=localcloud.%(region)s:partners" \
   --output-swift=published/ --max=1 --name-prefix="ubuntu/" \
   http://cloud-images.ubuntu.com/releases/ streams/v1/index.json
