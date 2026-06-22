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
 * اسم الملف: Meal.java
 * الوصف: صف يمثل وجبة في قائمة المطعم، يرث من صف MenuItem
 */

// Meal class representing a food item — inherits from MenuItem
public class Meal extends MenuItem {

    // Indicates whether the meal includes extras (fries, salad, extra sauce, etc.)
    private boolean hasExtras;

    // Constructor: receives meal id, name, price, and whether it has extras
    public Meal(int itemId, String name, double price, boolean hasExtras) {
        super(itemId, name, price);
        this.hasExtras = hasExtras;
    }

    // If meal has extras, add 15% to the base price; otherwise price stays the same
    @Override
    public double calculateFinalPrice() {
        if (hasExtras) {
            return price * 1.15;
        }
        return price;
    }

    // Display meal info and whether it has extras
    @Override
    public void displayInfo() {
        super.displayInfo();
        System.out.println("Has Extras: " + (hasExtras ? "Yes" : "No"));
        System.out.printf("Final Price: %.2f%n", calculateFinalPrice());
    }
}
