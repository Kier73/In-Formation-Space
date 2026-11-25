.section .multiboot,"a"
.align 4
.long 0x1badb002,0,-0x1badb002
.section .text.boot,"ax"
.code32
.global _start
_start:
    cli
    cld
    cmp $0x2badb002,%eax
    jne halt32
    mov $stack_top,%esp
    /* Zero page tables explicitly. */
    mov $pml4,%edi
    xor %eax,%eax
    mov $3072,%ecx
    rep stosl
    mov $pdpt,%eax
    or $3,%eax
    mov %eax,pml4
    mov $pd,%eax
    or $3,%eax
    mov %eax,pdpt
    /* First 1 GiB identity map, 2 MiB pages. */
    mov $pd,%edi
    mov $0x83,%eax
    mov $512,%ecx
1:  mov %eax,(%edi)
    add $8,%edi
    add $0x200000,%eax
    loop 1b
    mov %cr4,%eax
    or $0x20,%eax
    mov %eax,%cr4
    mov $pml4,%eax
    mov %eax,%cr3
    mov $0xc0000080,%ecx
    rdmsr
    or $0x100,%eax
    wrmsr
    lgdt gdt_ptr
    mov %cr0,%eax
    or $0x80000000,%eax
    mov %eax,%cr0
    ljmp $8,$long_start
halt32: hlt
    jmp halt32
.code64
long_start:
    mov $16,%ax
    mov %ax,%ds
    mov %ax,%es
    mov %ax,%ss
    lea stack_top(%rip),%rsp
    xor %ebp,%ebp
    call kernel_main
1:  cli
    hlt
    jmp 1b
.align 8
gdt:
    .quad 0,0x00af9a000000ffff,0x00cf92000000ffff
gdt_ptr:
    .word 23
    .long gdt
.section .bss,"aw",@nobits
.align 4096
pml4: .skip 4096
pdpt: .skip 4096
pd: .skip 4096
.align 16
.skip 32768
stack_top:
.section .note.GNU-stack,"",@progbits
