TENV := ./tools/tenv

PUBKEY := examples/keys/example.pub
PUBKEYS := $(PUBKEY)
SECKEY := examples/keys/example.sec

example_sstream_files := $(wildcard examples/*/streams/v1/*.json)

EXDATA_SIGN ?= 1
ifeq ($(EXDATA_SIGN),1)
    EXDATA_SIGN_ARG := --sign
endif

build:
	@echo nothing to do for $@

test: examples-sign
	$(TENV) nosetests3 -v tests/
test2: examples-sign
	$(TENV) nosetests -v tests/
lint:
	./tools/run-pylint

pep8:
	./tools/run-pep8

check: lint pep8 test test2

exdata: exdata/fake exdata/data

exdata/data: exdata-query gnupg
	$(TENV) env REAL_DATA=1 ./tools/make-test-data $(EXDATA_SIGN_ARG) exdata-query/ exdata/data

exdata/fake: exdata-query gnupg
	$(TENV) ./tools/make-test-data $(EXDATA_SIGN_ARG) exdata-query/ exdata/fake

exdata-query:
	rsync -avz --delete --exclude "FILE_DATA_CACHE" --exclude ".bzr/*" cloud-images.ubuntu.com::uec-images/query/ exdata-query

$(PUBKEY) $(SECKEY):
	@mkdir -p $$(dirname "$(PUBKEY)") $$(dirname "$(SECKEY)")
	$(TENV) gen-example-key $(PUBKEY) $(SECKEY)

gnupg: gnupg/README

gnupg/README: $(PUBKEYS) $(SECKEY)
	rm -Rf gnupg
	@umask 077 && mkdir -p gnupg
	$(TENV) gpg --import $(SECKEY) >/dev/null 2>&1
	for pubkey in $(PUBKEYS); do \
	  $(TENV) gpg-trust-pubkey $$pubkey; done
	@echo "this is used by $(TENV) as the gpg directory" > gnupg/README

# this is less than ideal, but Make and ':' in targets do not work together
# so instead of proper rules, we have this phoney rule that makes the
# targets.  This would probably cause issue with -j.
examples-sign: gnupg
	@for f in $(example_sstream_files); do \
		[ "$$f.gpg" -nt "$$f" -a "$${f%.json}.sjson" -nt "$$f" ] || \
		{ echo "$(TENV) js2signed $$f" 1>&2; $(TENV) js2signed $$f; } || exit; \
	done


.PHONY: check exdata/fake exdata/data exdata-query examples-sign test test2
