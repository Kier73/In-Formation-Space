/* VLM-001 independent Multiboot 1 word-machine substrate, GNU as i386. */
.section .multiboot,"a"
.align 4
.long 0x1badb002, 0, -(0x1badb002)
.section .text
.code32
.global _start
_start:
    cli
    mov $stack_top,%esp
    cld
    cmp $0x2badb002,%eax
    jne halt
    /* COM1, 115200 baud, 8N1 */
    mov $0x3f9,%dx
    xor %al,%al
    outb %al,%dx
    mov $0x3fb,%dx
    mov $0x80,%al
    outb %al,%dx
    mov $0x3f8,%dx
    mov $1,%al
    outb %al,%dx
    mov $0x3f9,%dx
    xor %al,%al
    outb %al,%dx
    mov $0x3fb,%dx
    mov $3,%al
    outb %al,%dx
    mov $0x3fa,%dx
    mov $0xc7,%al
    outb %al,%dx
    mov $0x3fc,%dx
    mov $3,%al
    outb %al,%dx
    mov $banner,%esi
    call puts
prompt:
    mov $prompt_str,%esi
    call puts
    call getc
    cmp $'q',%al
    je exit
    cmp $'a',%al
    je add_cmd
    cmp $'m',%al
    je mul_cmd
    cmp $'x',%al
    je xor_cmd
    cmp $'j',%al
    je jump_cmd
    cmp $'n',%al
    je and_cmd
    cmp $'l',%al
    je lt_cmd
    cmp $'s',%al
    je select_cmd
    cmp $10,%al
    je prompt
    cmp $13,%al
    je prompt
    mov $help,%esi
    call puts
    jmp prompt
/* Commands use fixed-width eight-hex-digit operands, no spaces. */
add_cmd:
    call hexin
    push %eax
    call hexin
    pop %ebx
    add %ebx,%eax
    jmp result
mul_cmd:
    call hexin
    push %eax
    call hexin
    pop %ebx
    imul %ebx,%eax
    jmp result
xor_cmd:
    call hexin
    push %eax
    call hexin
    pop %ebx
    xor %ebx,%eax
    jmp result
and_cmd:
    call hexin
    push %eax
    call hexin
    pop %ebx
    and %ebx,%eax
    jmp result
lt_cmd:
    call hexin
    push %eax
    call hexin
    pop %ebx
    cmp %eax,%ebx
    setb %al
    movzbl %al,%eax
    jmp result
select_cmd:
    call hexin
    push %eax
    call hexin
    push %eax
    call hexin
    pop %ebx
    pop %ecx
    test %ecx,%ecx
    cmovnz %ebx,%eax
    jmp result
/* j A B X N -- exact composition by squaring, N is a 32-bit word */
jump_cmd:
    call hexin
    push %eax
    call hexin
    push %eax
    call hexin
    push %eax
    call hexin
    mov %eax,%ecx
    pop %esi
    pop %ebx
    pop %eax
    /* eax=a, ebx=b, esi=x, ecx=n */
1:  test %ecx,%ecx
    jz 3f
    test $1,%ecx
    jz 2f
    imul %eax,%esi
    add %ebx,%esi
2:  mov %ebx,%edi
    imul %eax,%ebx
    add %edi,%ebx
    imul %eax,%eax
    shr $1,%ecx
    jmp 1b
3:  mov %esi,%eax
    jmp result
result:
    push %eax
    mov $result_str,%esi
    call puts
    pop %eax
    call hexout
    mov $newline,%esi
    call puts
    jmp prompt
exit:
    mov $0xf4,%dx
    mov $0x10,%al
    outb %al,%dx
halt:
    cli
    hlt
    jmp halt
putc:
    push %eax
    push %edx
    mov %al,%ah
    mov $0x3fd,%dx
1:  inb %dx,%al
    test $0x20,%al
    jz 1b
    mov $0x3f8,%dx
    mov %ah,%al
    outb %al,%dx
    pop %edx
    pop %eax
    ret
getc:
    push %edx
    mov $0x3fd,%dx
1:  inb %dx,%al
    test $1,%al
    jz 1b
    mov $0x3f8,%dx
    inb %dx,%al
    pop %edx
    ret
puts:
    lodsb
    test %al,%al
    jz 1f
    call putc
    jmp puts
1:  ret
hexin:
    push %ebx
    push %ecx
    xor %ebx,%ebx
    mov $8,%ecx
1:  call getc
    cmp $'0',%al
    jb bad
    cmp $'9',%al
    jbe 2f
    or $0x20,%al
    cmp $'a',%al
    jb bad
    cmp $'f',%al
    ja bad
    sub $('a'-10),%al
    jmp 3f
2:  sub $'0',%al
3:  shl $4,%ebx
    movzbl %al,%eax
    or %eax,%ebx
    loop 1b
    mov %ebx,%eax
    pop %ecx
    pop %ebx
    ret
bad:
    /* Abort entire command, including partially pushed operands. */
    mov $stack_top,%esp
    mov $err,%esi
    call puts
    jmp prompt
hexout:
    mov %eax,%ebx
    mov $8,%ecx
1:  rol $4,%ebx
    mov %ebx,%eax
    and $15,%eax
    mov digits(%eax),%al
    call putc
    loop 1b
    ret
.section .rodata
banner: .asciz "VLM-001 native word machine\n"
prompt_str: .asciz "vl> "
help: .asciz "a/m/x/n/l + two hex words; s + condition true false; j + A B X N; q\n"
result_str: .asciz "RESULT "
newline: .asciz "\n"
err: .asciz "REJECT\n"
digits: .ascii "0123456789abcdef"
.section .bss
.align 16
.space 16384
stack_top:
