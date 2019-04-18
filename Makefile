TARGETS=peer node rpc

all: $(TARGETS)

%: %.py
	cp $@.py pds18-$@
	chmod u+x pds18-$@