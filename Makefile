test:
	nosetests -v tests/

exdata: exdata/cpc exdata/images exdata/images.fake

exdata/cpc: exdata-query 
	PYTHONPATH=$(PYTHONPATH):$(CURDIR) ./tools/make-test-cpc-data exdata-query/ exdata/cpc

exdata/images: exdata-query
	PYTHONPATH=$(PYTHONPATH):$(CURDIR) REAL_DATA=1 ./tools/make-test-dl-data exdata-query/ exdata/images

exdata/images.fake: exdata-query
	PYTHONPATH=$(PYTHONPATH):$(CURDIR) ./tools/make-test-dl-data exdata-query/ exdata/images.fake

exdata-query:
	rsync -avz --delete --exclude HASH_CACHE --exclude ".bzr/*" cloud-images.ubuntu.com::uec-images/query/ exdata-query

.PHONY: exdata/cpc exdata/images exdata-query exdata/images.fake
