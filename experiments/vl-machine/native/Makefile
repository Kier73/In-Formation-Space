AS = as
LD = ld
all: vlm.elf
vlm.o: boot.S
	$(AS) --32 -o $@ $<
vlm.elf: vlm.o link.ld
	$(LD) -m elf_i386 -T link.ld -o $@ vlm.o
test: vlm.elf
	python3 test_boot.py
clean:
	rm -f vlm.o vlm.elf
