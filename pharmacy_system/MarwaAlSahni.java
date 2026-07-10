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

import java.util.Scanner;

// ================================================================
// Node: عقدة في سلسلة التصادم (Chaining)
// تخزن معلومات دواء واحد وتشير للعقدة التالية في السلسلة
// ================================================================
class Node {
    int    barcode; // رقم الباركود (4 أرقام)
    String name;    // اسم الدواء
    double price;   // سعر الدواء
    Node   next;    // مؤشر للعقدة التالية في حالة التصادم

    Node(int barcode, String name, double price) {
        this.barcode = barcode;
        this.name    = name;
        this.price   = price;
        this.next    = null;
    }
}

// ================================================================
// PharmacyHashTable: جدول التقطيع لإدارة أدوية الصيدلية
// حجم الجدول 1000 خلية — دالة التقطيع: barcode % 1000
// معالجة التصادم عبر السلاسل المتشعبة (Chaining)
// ================================================================
class PharmacyHashTable {

    private static final int TABLE_SIZE = 1000; // حجم جدول التقطيع
    private Node[] table;                        // مصفوفة رؤوس السلاسل

    PharmacyHashTable() {
        table = new Node[TABLE_SIZE]; // تهيئة كل الخلايا بـ null
    }

    // -------------------------------------------------------
    // دالة التقطيع: باقي القسمة (Division Method)
    // مثال: barcode=1573 => 1573 % 1000 = 573
    // -------------------------------------------------------
    private int hashFunction(int barcode) {
        return barcode % TABLE_SIZE;
    }

    // ================================================================
    // 1. الإدراج (Insertion): إضافة دواء جديد إلى النظام
    //    يُحسب موقع التخزين من رقم الباركود مباشرةً
    // ================================================================
    public void insert(int barcode, String name, double price) {
        int index = hashFunction(barcode); // حساب موقع التخزين O(1)

        // فحص إذا كان الباركود موجوداً مسبقاً في السلسلة
        Node current = table[index];
        while (current != null) {
            if (current.barcode == barcode) {
                System.out.println("  [!] الباركود " + barcode + " مسجل مسبقاً في النظام.");
                return;
            }
            current = current.next;
        }

        // إدراج العقدة الجديدة في رأس السلسلة (أسرع: O(1))
        Node newNode = new Node(barcode, name, price);
        newNode.next = table[index];
        table[index] = newNode;
        System.out.println("  [+] تمت إضافة الدواء: " + name
                + " | موقع التخزين: " + index);
    }

    // ================================================================
    // 2. البحث اللحظي (Retrieval): استرجاع معلومات دواء بالباركود
    //    يصل للموقع مباشرةً في خطوة واحدة — O(1)
    // ================================================================
    public void retrieve(int barcode) {
        int index    = hashFunction(barcode); // الانتقال المباشر للموقع
        Node current = table[index];

        // البحث داخل سلسلة الموقع
        while (current != null) {
            if (current.barcode == barcode) {
                System.out.println("  [✓] تم العثور على الدواء:");
                System.out.println("      الاسم  : " + current.name);
                System.out.println("      السعر  : " + current.price + " ل.س");
                return;
            }
            current = current.next;
        }
        System.out.println("  [✗] لا يوجد دواء بالباركود " + barcode + " في النظام.");
    }

    // ================================================================
    // 3. معالجة التصادم (Collision Handling): عرض توضيحي
    //    مثال: 1573 و 2573 كلاهما يُعطيان نفس الموقع 573
    //    الحل: ربطهما في سلسلة متشعبة بنفس الخلية
    // ================================================================
    public void demonstrateCollision() {
        int barcode1 = 1573, barcode2 = 2573; // باركودان مختلفان
        int index1   = hashFunction(barcode1);
        int index2   = hashFunction(barcode2);

        System.out.println("  باركود " + barcode1 + " => موقع التخزين: " + index1);
        System.out.println("  باركود " + barcode2 + " => موقع التخزين: " + index2);
        System.out.println("  => تصادم! يتم ربطهما في سلسلة بنفس الخلية.");

        insert(barcode1, "Paracetamol 500mg", 150);
        insert(barcode2, "Aspirin 100mg",     200);

        System.out.println("  => كلا الدواءين محفوظان بدون ضياع أي سجل.");
    }

    // ================================================================
    // 4. التحديث (Update): تعديل سعر دواء بالباركود مباشرةً
    //    يتوجه النظام للموقع دون المرور على بقية العناصر
    // ================================================================
    public void update(int barcode, double newPrice) {
        int index    = hashFunction(barcode); // الانتقال المباشر O(1)
        Node current = table[index];

        while (current != null) {
            if (current.barcode == barcode) {
                double oldPrice = current.price;
                current.price   = newPrice; // تعديل السعر مباشرةً
                System.out.println("  [✓] تم تحديث سعر: " + current.name);
                System.out.println("      السعر القديم: " + oldPrice + " ل.س");
                System.out.println("      السعر الجديد: " + newPrice + " ل.س");
                return;
            }
            current = current.next;
        }
        System.out.println("  [✗] لا يوجد دواء بالباركود " + barcode + " في النظام.");
    }
}

// ================================================================
// الصف الرئيسي: يجمع جميع العمليات ويوفر قائمة تفاعلية للمستخدم
// ================================================================
public class MarwaAlSahni {

    public static void main(String[] args) {
        Scanner           scanner  = new Scanner(System.in);
        PharmacyHashTable pharmacy = new PharmacyHashTable();

        System.out.println("============================================");
        System.out.println(" نظام الاستعلام الفوري — صيدلية الوادي");
        System.out.println("============================================");

        int choice = 0;
        while (choice != 5) {
            System.out.println("\n--- القائمة الرئيسية ---");
            System.out.println("1. إضافة دواء جديد          (Insertion)");
            System.out.println("2. البحث عن دواء بالباركود  (Retrieval)");
            System.out.println("3. عرض معالجة التصادم       (Collision Handling)");
            System.out.println("4. تحديث سعر دواء           (Update)");
            System.out.println("5. خروج");
            System.out.print("اختر رقم العملية: ");
            choice = scanner.nextInt();
            scanner.nextLine();

            switch (choice) {

                case 1: // ---- إضافة دواء ----
                    System.out.print("رقم الباركود (4 أرقام): ");
                    int barcode = scanner.nextInt();
                    scanner.nextLine();
                    System.out.print("اسم الدواء: ");
                    String name = scanner.nextLine();
                    System.out.print("السعر (ل.س): ");
                    double price = scanner.nextDouble();
                    scanner.nextLine();
                    pharmacy.insert(barcode, name, price);
                    break;

                case 2: // ---- البحث ----
                    System.out.print("رقم الباركود: ");
                    pharmacy.retrieve(scanner.nextInt());
                    scanner.nextLine();
                    break;

                case 3: // ---- التصادم ----
                    pharmacy.demonstrateCollision();
                    break;

                case 4: // ---- التحديث ----
                    System.out.print("رقم الباركود: ");
                    int bc = scanner.nextInt();
                    scanner.nextLine();
                    System.out.print("السعر الجديد (ل.س): ");
                    double np = scanner.nextDouble();
                    scanner.nextLine();
                    pharmacy.update(bc, np);
                    break;

                case 5:
                    System.out.println("\n إلى اللقاء!");
                    break;

                default:
                    System.out.println("  [!] اختيار غير صحيح، حاول مجدداً.");
            }
        }
        scanner.close();
    }
}
