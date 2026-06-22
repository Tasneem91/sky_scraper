/*
 * الجمهورية العربية السورية - وزارة السياحة
 * الهيئة العامة للتدريب السياحي والفندقي
 * مركز الوادي للتأهيل والتدريب السياحي والفندقي
 *
 * مشروع مادة البرمجة 2
 * نظام إدارة مطعم داخل فندق
 * دبلوم في العلوم السياحية
 * اختصاص إدارة سياحية وتطبيقات تقانة معلومات
 * السنة الأولى - الفصل الثاني
 *
 * اسم الطالبة: مروة الصحني
 *
 * اسم الملف: Drink.java
 * الوصف: صف يمثل مشروباً في قائمة المطعم، يرث من صف MenuItem
 */

// Drink class representing a beverage — inherits from MenuItem
public class Drink extends MenuItem {

    // Size of the drink: Small, Medium, or Large
    private String size;

    // Constructor: receives drink id, name, price, and size
    public Drink(int itemId, String name, double price, String size) {
        super(itemId, name, price);
        this.size = size;
    }

    // Small: same price | Medium: +10% | Large: +20%
    @Override
    public double calculateFinalPrice() {
        if (size.equalsIgnoreCase("Medium")) {
            return price * 1.10;
        } else if (size.equalsIgnoreCase("Large")) {
            return price * 1.20;
        }
        return price; // Small
    }

    // Display drink info including its size
    @Override
    public void displayInfo() {
        super.displayInfo();
        System.out.println("Size: " + size);
        System.out.printf("Final Price: %.2f%n", calculateFinalPrice());
    }
}
