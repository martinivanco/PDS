TARGETS=peer node rpc

all: $(TARGETS)

%: %.py
	ln -s $@.py pds18-$@
	chmod u+x pds18-$@