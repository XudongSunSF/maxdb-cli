/**
 * examples/use_after_free.cpp
 *
 * Classic use-after-free bug: delete_list() frees the current node
 * before reading its ->next pointer.
 *
 * Compile:
 *   g++ -g -O0 -fsanitize=address -o use_after_free use_after_free.cpp
 *   # then debug with:
 *   udb ./use_after_free
 *
 * Expected crash:
 *   SIGSEGV in delete_list() at line 21 (head = head->next after free)
 *
 * Time-travel session:
 *   (udb) run
 *   (udb) break 20        # break before delete
 *   (udb) continue
 *   (udb) step            # execute the delete
 *   (udb) step            # crash: use-after-free
 *   (udb) explain         # Claude AI root-cause analysis
 *   (udb) reverse-step    # step back to safe state
 */

#include <iostream>
#include <cassert>

struct Node {
    int   value;
    Node* next;
};

/// BUG: deletes head before saving head->next
void delete_list(Node* head) {
    while (head) {
        delete head;        // line 20: memory freed here
        head = head->next;  // line 21: UNDEFINED BEHAVIOUR — use-after-free!
    }
}

/// Correct version (for reference — uncomment to compare)
// void delete_list(Node* head) {
//     while (head) {
//         Node* next = head->next;   // save next BEFORE delete
//         delete head;
//         head = next;
//     }
// }

Node* build_list(int n) {
    Node* head = nullptr;
    for (int i = n; i >= 1; --i) {
        Node* node = new Node{i, head};
        head = node;
    }
    return head;
}

void print_list(const Node* head) {
    std::cout << "[ ";
    while (head) {
        std::cout << head->value;
        if (head->next) std::cout << " → ";
        head = head->next;
    }
    std::cout << " ]\n";
}

int main() {
    Node* list = build_list(5);

    std::cout << "Built list: ";
    print_list(list);

    std::cout << "Deleting list...\n";
    delete_list(list);   // ← crashes here

    std::cout << "Done.\n";
    return 0;
}
