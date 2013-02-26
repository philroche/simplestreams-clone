TENV := ./tools/tenv

PUBKEY := examples/keys/example.pub
SECKEY := examples/keys/example.sec


test:
	nosetests -v tests/

exdata: exdata/cpc exdata/images exdata/images.fake

exdata/cpc: exdata-query gnupg
	$(TENV) ./tools/make-test-cpc-data --sign exdata-query/ exdata/cpc

exdata/images: exdata-query gnupg
	$(TENV) env REAL_DATA=1 ./tools/make-test-dl-data --sign exdata-query/ exdata/images

exdata/images.fake: exdata-query gnupg
	$(TENV) ./tools/make-test-dl-data --sign exdata-query/ exdata/images.fake

exdata-query:
	rsync -avz --delete --exclude HASH_CACHE --exclude ".bzr/*" cloud-images.ubuntu.com::uec-images/query/ exdata-query

$(PUBKEY) $(SECKEY):
	@mkdir -p $$(dirname "$(PUBKEY)") $$(dirname "$(SECKEY)")
	$(TENV) gen-example-key $(PUBKEY) $(SECKEY)

gnupg: gnupg/README

gnupg/README: $(PUBKEY) $(SECKEY)
	rm -Rf gnupg
	@umask 077 && mkdir -p gnupg
	$(TENV) gpg --import $(SECKEY) >/dev/null 2>&1
	$(TENV) gpg --import $(PUBKEY) >/dev/null 2>&1
	fp=$$($(TENV) gpg --with-fingerprint --with-colons $(PUBKEY) \
	    | awk -F: '$$1 == "fpr" {print $$10}') && \
	    echo "$${fp}:6:" | $(TENV) gpg --import-ownertrust
	@echo "this is used by $(TENV) as the gpg directory" > gnupg/README

.PHONY: exdata/cpc exdata/images exdata-query exdata/images.fake
