CC = gcc
CFLAGS = -std=c11 -O2 -Wall -Wextra -Werror
FREE = -ffreestanding -fno-pic -fno-pie -fno-stack-protector -mno-red-zone -mgeneral-regs-only
all: vlm64.elf libcore.so
boot.o: boot.S
	$(CC) -m64 -c $< -o $@
%.o: %.c core.h
	$(CC) $(CFLAGS) $(FREE) -c $< -o $@
vlm64.raw: boot.o core.o kernel.o link.ld
	ld -m elf_x86_64 -T link.ld -o $@ boot.o core.o kernel.o
vlm64.elf: vlm64.raw
	objcopy -O elf32-i386 $< $@
libcore.so: core.c core.h
	$(CC) $(CFLAGS) -shared -fPIC core.c -o $@
clean:
	rm -f *.o *.raw *.elf *.so
