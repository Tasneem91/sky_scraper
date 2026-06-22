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
 * اسم الملف: Employee.java
 * الوصف: صف يمثل موظفاً يعمل في مطعم الفندق
 * يوضح مفهوم التحميل الزائد للبواني (Constructor Overloading)
 */

// Employee class representing a staff member in the hotel restaurant
public class Employee {

    private int employeeId;
    private String name;
    private String role;
    private double salary;

    // Constructor Overloading — full constructor with all employee data
    public Employee(int employeeId, String name, String role, double salary) {
        this.employeeId = employeeId;
        this.name = name;
        this.role = role;
        this.salary = salary;
    }

    // Constructor Overloading — minimal constructor: role defaults to Waiter, salary to 300
    public Employee(int employeeId, String name) {
        this.employeeId = employeeId;
        this.name = name;
        this.role = "Waiter";
        this.salary = 300;
    }

    // Display all employee information
    public void displayEmployeeInfo() {
        System.out.println("Employee ID: " + employeeId);
        System.out.println("Name: " + name);
        System.out.println("Role: " + role);
        System.out.println("Salary: " + salary);
    }

    public String getName() {
        return name;
    }
}
