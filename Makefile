TENV := ./tools/tenv

EXDATA_SIGN ?= 1
ifeq ($(EXDATA_SIGN),1)
    EXDATA_SIGN_ARG := --sign
endif

build:
	@echo nothing to do for $@

test: test2 test3

test3: examples-sign
	$(TENV) nosetests3 -v tests/
test2: examples-sign
	$(TENV) nosetests -v tests/

lint: pyflakes

pyflakes: pyflakes2 pyflakes3

pyflakes2:
	$(TENV) env ./tools/run-pyflakes

pyflakes3:
	$(TENV) env ./tools/run-pyflakes3

pep8:
	./tools/run-pep8

check: lint pep8 test

exdata: exdata/fake exdata/data

exdata/data: exdata-query gnupg
	$(TENV) env REAL_DATA=1 ./tools/make-test-data $(EXDATA_SIGN_ARG) exdata-query/ exdata/data

exdata/fake: exdata-query gnupg
	$(TENV) ./tools/make-test-data $(EXDATA_SIGN_ARG) exdata-query/ exdata/fake

exdata-query:
	rsync -avz --delete --exclude "FILE_DATA_CACHE" --exclude ".bzr/*" cloud-images.ubuntu.com::uec-images/query/ exdata-query

gnupg:
	./tools/gnupg

examples-sign: gnupg
	./tools/example-sign

.PHONY: check exdata/fake exdata/data exdata-query examples-sign test test2 test3 lint lint2 lint3
