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
 * اسم الملف: Table.java
 * الوصف: صف يمثل طاولة داخل مطعم الفندق
 * يوضح مفهوم التحميل الزائد للبواني (Constructor Overloading)
 */

// Table class representing a dining table inside the hotel restaurant
public class Table {

    private int tableNumber;
    private int numberOfSeats;
    private boolean isReserved;

    // Constructor Overloading — full constructor with reservation status
    public Table(int tableNumber, int numberOfSeats, boolean isReserved) {
        this.tableNumber = tableNumber;
        this.numberOfSeats = numberOfSeats;
        this.isReserved = isReserved;
    }

    // Constructor Overloading — table is not reserved by default
    public Table(int tableNumber, int numberOfSeats) {
        this.tableNumber = tableNumber;
        this.numberOfSeats = numberOfSeats;
        this.isReserved = false;
    }

    // Mark this table as reserved
    public void reserveTable() {
        isReserved = true;
    }

    // Display table information
    public void displayTableInfo() {
        System.out.println("Table Number: " + tableNumber);
        System.out.println("Number of Seats: " + numberOfSeats);
        System.out.println("Reserved: " + (isReserved ? "Yes" : "No"));
    }

    public int getTableNumber() {
        return tableNumber;
    }
}
