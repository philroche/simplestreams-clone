TENV := ./tools/tenv

EXDATA_SIGN ?= 1
ifeq ($(EXDATA_SIGN),1)
    EXDATA_SIGN_ARG := --sign
endif

build:
	@echo nothing to do for $@

test: test2 test3 flake8

test3: examples-sign
	$(TENV) nosetests3 -v tests/
test2: examples-sign
	$(TENV) nosetests -v tests/

flake8:
	./tools/run-flake8

exdata: exdata/fake exdata/data

exdata/data: exdata-query gnupg
	$(TENV) env REAL_DATA=1 ./tools/make-test-data $(EXDATA_SIGN_ARG) exdata-query/ exdata/data

exdata/fake: exdata-query gnupg
	$(TENV) ./tools/make-test-data $(EXDATA_SIGN_ARG) exdata-query/ exdata/fake

exdata-query:
	rsync -avz --delete --exclude "FILE_DATA_CACHE" --exclude ".bzr/*" cloud-images.ubuntu.com::uec-images/query/ exdata-query

gnupg: gnupg/README

gnupg/README:
	./tools/create-gpgdir

examples-sign: gnupg/README
	$(TENV) ./tools/sign-examples

.PHONY: exdata/fake exdata/data exdata-query examples-sign flake8 test test2 test3
