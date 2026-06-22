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
 * اسم الملف: Main.java
 * الوصف: الصف الرئيسي — يقرأ بيانات الموظف والطاولة والطلب من المستخدم
 */

import java.util.Scanner;

// Main class — entry point for the Hotel Restaurant Management System
public class Main {

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);

        // --- Input employee data ---
        System.out.print("Enter employee id: ");
        int employeeId = scanner.nextInt();
        scanner.nextLine();

        System.out.print("Enter employee name: ");
        String employeeName = scanner.nextLine();

        System.out.print("Enter employee role: ");
        String employeeRole = scanner.nextLine();

        System.out.print("Enter employee salary: ");
        double employeeSalary = scanner.nextDouble();

        Employee employee = new Employee(employeeId, employeeName, employeeRole, employeeSalary);

        // --- Input table data ---
        System.out.print("Enter table number: ");
        int tableNumber = scanner.nextInt();

        System.out.print("Enter number of seats: ");
        int numberOfSeats = scanner.nextInt();

        Table table = new Table(tableNumber, numberOfSeats);
        table.reserveTable();

        // --- Input number of items ---
        System.out.print("Enter number of items in order: ");
        int numItems = scanner.nextInt();
        scanner.nextLine();

        Order order = new Order(1, table, employee, numItems);

        // --- Input each item ---
        for (int i = 1; i <= numItems; i++) {
            System.out.println("\nItem " + i + ":");
            System.out.print("Enter item type, 1 for Meal, 2 for Drink: ");
            int itemType = scanner.nextInt();
            scanner.nextLine();

            if (itemType == 1) {
                System.out.print("Enter meal id: ");
                int mealId = scanner.nextInt();
                scanner.nextLine();

                System.out.print("Enter meal name: ");
                String mealName = scanner.nextLine();

                System.out.print("Enter meal price: ");
                double mealPrice = scanner.nextDouble();
                scanner.nextLine();

                System.out.print("Does the meal have extras? ");
                boolean hasExtras = scanner.nextBoolean();
                scanner.nextLine();

                order.addItem(new Meal(mealId, mealName, mealPrice, hasExtras));

            } else {
                System.out.print("Enter drink id: ");
                int drinkId = scanner.nextInt();
                scanner.nextLine();

                System.out.print("Enter drink name: ");
                String drinkName = scanner.nextLine();

                System.out.print("Enter drink price: ");
                double drinkPrice = scanner.nextDouble();
                scanner.nextLine();

                System.out.print("Enter size: ");
                String size = scanner.nextLine();

                order.addItem(new Drink(drinkId, drinkName, drinkPrice, size));
            }
        }

        // --- Display complete order details ---
        order.displayOrderDetails();

        scanner.close();
    }
}
