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
 * اسم الملف: Order.java
 * الوصف: صف يمثل طلب زبون داخل المطعم
 * يستخدم تعدد الأشكال (Polymorphism) لتخزين الوجبات والمشروبات في نفس المصفوفة
 */

// Order class representing a customer order — stores both Meal and Drink in a MenuItem array
public class Order {

    private int orderId;
    private Table table;
    private Employee employee;
    private MenuItem[] items; // Meals and Drinks stored as MenuItem (polymorphism)
    private int itemCount;

    // Constructor: receives order id, table, employee, and max number of items
    public Order(int orderId, Table table, Employee employee, int maxItems) {
        this.orderId = orderId;
        this.table = table;
        this.employee = employee;
        this.items = new MenuItem[maxItems];
        this.itemCount = 0;
    }

    // Add a menu item (Meal or Drink) to the order
    public void addItem(MenuItem item) {
        if (itemCount < items.length) {
            items[itemCount] = item;
            itemCount++;
        }
    }

    // Sum the final prices of all items in the order
    public double calculateTotal() {
        double total = 0;
        for (int i = 0; i < itemCount; i++) {
            total += items[i].calculateFinalPrice();
        }
        return total;
    }

    // Display order id, table info, employee name, all items, and total price
    public void displayOrderDetails() {
        System.out.println("\nOrder Details:");
        System.out.println("Order ID: " + orderId);
        System.out.println("Table Number: " + table.getTableNumber());
        System.out.println("Employee: " + employee.getName());
        System.out.println("\nItems:");
        for (int i = 0; i < itemCount; i++) {
            System.out.printf("%s - Final Price: %.2f%n",
                    items[i].name, items[i].calculateFinalPrice());
        }
        System.out.printf("Total Price: %.2f%n", calculateTotal());
    }
}
