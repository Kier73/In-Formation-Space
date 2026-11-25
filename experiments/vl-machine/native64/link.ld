ENTRY(_start)
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }
SECTIONS {
 . = 1M;
 .multiboot : { KEEP(*(.multiboot)) } :text
 .text : { *(.text.boot) *(.text*) } :text
 .rodata : { *(.rodata*) } :text
 . = ALIGN(4096);
 .data : { *(.data*) } :data
 .bss : { *(.bss*) *(COMMON) } :data
 /DISCARD/ : { *(.eh_frame*) *(.note*) *(.comment*) }
}
