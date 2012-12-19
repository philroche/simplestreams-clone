This is an example client for syncing data from a remote source.

For example of what the server side data looks like:
 * look in doc/
 * generate your own from http://cloud-images.ubuntu.com/query data
   $ rsync -avz --delete --exclude ".bzr/*" \
       cloud-images.ubuntu.com::uec-images/query/ ci-query
   $ ./tools/make-test-cpc-data ci-query/ ex/cpc
   $ ./tools/make-test-dl-data ci-query/ ex/images
