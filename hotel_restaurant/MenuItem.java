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
 * اسم الملف: MenuItem.java
 * الوصف: صف مجرد يمثل أي عنصر يمكن بيعه في المطعم (وجبة أو مشروب)
 */

// Abstract class representing any item that can be sold in the restaurant
public abstract class MenuItem {

    protected String name;
    protected double price;
    protected int itemId;

    // Constructor: receives item id, name, and price
    public MenuItem(int itemId, String name, double price) {
        this.itemId = itemId;
        this.name = name;
        this.price = price;
    }

    // Display basic item information
    public void displayInfo() {
        System.out.println("Item ID: " + itemId);
        System.out.println("Name: " + name);
        System.out.println("Base Price: " + price);
    }

    // Abstract method: each subclass calculates its own final price
    public abstract double calculateFinalPrice();
}
