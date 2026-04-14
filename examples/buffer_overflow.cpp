/**
 * examples/buffer_overflow.cpp
 *
 * Stack buffer overflow: copy() writes past the end of a fixed-size array.
 *
 * Compile:
 *   g++ -g -O0 -fno-stack-protector -o buffer_overflow buffer_overflow.cpp
 *
 * Debug:
 *   udb ./buffer_overflow
 *
 * Session:
 *   (udb) run
 *   (udb) break copy     # break at function entry
 *   (udb) continue
 *   (udb) info locals    # watch buf[], i
 *   (udb) step           # step through the loop
 *   (udb) explain        # AI tells you when the overflow will happen
 *   (udb) watch buf[16]  # watchpoint on the byte past the end
 *   (udb) continue       # stop when corruption occurs
 */

#include <iostream>
#include <cstring>

constexpr int BUF_SIZE = 16;

struct Packet {
    char    buf[BUF_SIZE];   // fixed-size buffer
    int     checksum;        // corrupted when overflow occurs
    bool    valid;
};

/// BUG: no bounds check on i
void copy(Packet& pkt, const char* src) {
    int i = 0;
    while (src[i] != '\0') {
        pkt.buf[i] = src[i];   // writes past buf[BUF_SIZE-1] when src is long
        ++i;
    }
    pkt.buf[i] = '\0';
}

/// Safe version:
// void copy_safe(Packet& pkt, const char* src) {
//     strncpy(pkt.buf, src, BUF_SIZE - 1);
//     pkt.buf[BUF_SIZE - 1] = '\0';
// }

int compute_checksum(const Packet& pkt) {
    int sum = 0;
    for (char c : pkt.buf) sum += static_cast<unsigned char>(c);
    return sum;
}

int main() {
    Packet pkt{};
    pkt.checksum = 0xDEADBEEF;
    pkt.valid    = true;

    const char* payload = "Hello, this string is deliberately too long!";

    std::cout << "Before copy:\n";
    std::cout << "  checksum = 0x" << std::hex << pkt.checksum << "\n";
    std::cout << "  valid    = " << pkt.valid << "\n\n";

    copy(pkt, payload);   // ← overflows into checksum and valid

    std::cout << "After copy:\n";
    std::cout << "  buf      = \"" << pkt.buf << "\"\n";
    std::cout << "  checksum = 0x" << std::hex << pkt.checksum << "\n";
    std::cout << "  valid    = " << pkt.valid << "\n";

    if (!pkt.valid || pkt.checksum != 0xDEADBEEF) {
        std::cerr << "\nERROR: packet corrupted!\n";
        return 1;
    }

    return 0;
}
