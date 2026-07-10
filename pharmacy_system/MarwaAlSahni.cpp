/*
 * وزارة السياحة — مركز الوادي للتأهيل والتدريب السياحي
 * دبلومة تقانة المعلومات
 *
 * مشروع مادة بنى المعطيات
 * نظام الاستعلام الفوري في قاعدة بيانات "صيدلية الوادي"
 *
 * اسم الطالبة: مروة الصحني
 * أستاذ المادة: م. زكريا صافي
 */

#include <iostream>
#include <string>
using namespace std;

const int TABLE_SIZE = 1000; // حجم جدول التقطيع

// عقدة في سلسلة التصادم — تخزن بيانات دواء واحد
struct Node {
    int barcode;
    string name;
    double price;
    Node* next;
    Node(int b, string n, double p) : barcode(b), name(n), price(p), next(nullptr) {}
};

Node* table[TABLE_SIZE]; // مصفوفة رؤوس السلاسل

// دالة التقطيع — Division Method: barcode % 1000
int hashFunction(int barcode) {
    return barcode % TABLE_SIZE;
}

// إضافة دواء جديد إلى النظام
void insert(int barcode, string name, double price) {
    int index = hashFunction(barcode); // حساب موقع التخزين
    Node* cur = table[index];
    // التحقق من عدم تكرار الباركود
    while (cur != nullptr) {
        if (cur->barcode == barcode) {
            cout << "  [!] الباركود " << barcode << " مسجل مسبقاً." << endl;
            return;
        }
        cur = cur->next;
    }
    // إدراج العقدة في رأس السلسلة
    Node* newNode = new Node(barcode, name, price);
    newNode->next = table[index];
    table[index] = newNode;
    cout << "  [+] تمت الإضافة: " << name << " | موقع: " << index << endl;
}

// البحث عن دواء بالباركود — O(1)
void retrieve(int barcode) {
    int index = hashFunction(barcode); // الانتقال المباشر للموقع
    Node* cur = table[index];
    while (cur != nullptr) {
        if (cur->barcode == barcode) {
            cout << "  [✓] الاسم  : " << cur->name << endl;
            cout << "      السعر  : " << cur->price << " ل.س" << endl;
            return;
        }
        cur = cur->next;
    }
    cout << "  [✗] لا يوجد دواء بالباركود " << barcode << endl;
}

// عرض معالجة التصادم — 1573 و 2573 كلاهما يعطيان الموقع 573
void demonstrateCollision() {
    int b1 = 1573, b2 = 2573;
    cout << "  باركود " << b1 << " => موقع التخزين: " << hashFunction(b1) << endl;
    cout << "  باركود " << b2 << " => موقع التخزين: " << hashFunction(b2) << endl;
    cout << "  => تصادم — يتم ربطهما في سلسلة بنفس الخلية." << endl;
    insert(b1, "Paracetamol 500mg", 150);
    insert(b2, "Aspirin 100mg", 200);
    cout << "  => كلا الدواءين محفوظان بدون ضياع أي سجل." << endl;
}

// تحديث سعر دواء — ينتقل مباشرة للموقع دون المرور على بقية العناصر
void update(int barcode, double newPrice) {
    int index = hashFunction(barcode);
    Node* cur = table[index];
    while (cur != nullptr) {
        if (cur->barcode == barcode) {
            double oldPrice = cur->price;
            cur->price = newPrice; // تعديل السعر مباشرة
            cout << "  [✓] تم تحديث: " << cur->name << endl;
            cout << "      السعر القديم: " << oldPrice << " ل.س" << endl;
            cout << "      السعر الجديد: " << newPrice << " ل.س" << endl;
            return;
        }
        cur = cur->next;
    }
    cout << "  [✗] لا يوجد دواء بالباركود " << barcode << endl;
}

int main() {
    // تهيئة جميع خلايا الجدول بـ nullptr
    for (int i = 0; i < TABLE_SIZE; i++) table[i] = nullptr;

    cout << "============================================" << endl;
    cout << " نظام الاستعلام الفوري — صيدلية الوادي" << endl;
    cout << "============================================" << endl;

    int choice = 0;
    while (choice != 5) {
        cout << "\n--- القائمة الرئيسية ---" << endl;
        cout << "1. إضافة دواء جديد          (Insertion)" << endl;
        cout << "2. البحث عن دواء بالباركود  (Retrieval)" << endl;
        cout << "3. عرض معالجة التصادم       (Collision Handling)" << endl;
        cout << "4. تحديث سعر دواء           (Update)" << endl;
        cout << "5. خروج" << endl;
        cout << "اختر رقم العملية: ";
        cin >> choice;
        cin.ignore();

        switch (choice) {
            case 1: {
                int bc;
                string nm;
                double pr;
                cout << "رقم الباركود (4 أرقام): ";
                cin >> bc;
                cin.ignore();
                cout << "اسم الدواء: ";
                getline(cin, nm);
                cout << "السعر (ل.س): ";
                cin >> pr;
                cin.ignore();
                insert(bc, nm, pr);
                break;
            }
            case 2: {
                int bc;
                cout << "رقم الباركود: ";
                cin >> bc;
                cin.ignore();
                retrieve(bc);
                break;
            }
            case 3:
                demonstrateCollision();
                break;
            case 4: {
                int bc;
                double np;
                cout << "رقم الباركود: ";
                cin >> bc;
                cin.ignore();
                cout << "السعر الجديد (ل.س): ";
                cin >> np;
                cin.ignore();
                update(bc, np);
                break;
            }
            case 5:
                cout << "\n إلى اللقاء!" << endl;
                break;
            default:
                cout << "  [!] اختيار غير صحيح، حاول مجدداً." << endl;
        }
    }

    return 0;
}
