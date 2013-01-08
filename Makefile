test:
	nosetests -v tests/

exdata: exdata/cpc exdata/images

exdata/cpc: exdata-query 
	./tools/make-test-cpc-data exdata-query/ exdata/cpc

exdata/images: exdata-query
	./tools/make-test-dl-data exdata-query/ exdata/images

exdata-query:
	rsync -avz --delete --exclude ".bzr/*" cloud-images.ubuntu.com::uec-images/query/ exdata-query
