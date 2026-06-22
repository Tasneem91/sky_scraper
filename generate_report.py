"""
PDF report generator for Programming 2 project — Hotel Restaurant Management System
Student: مروة الصحني  |  Al-Wadi Center
"""

from fpdf import FPDF
from fpdf.enums import XPos, YPos
import arabic_reshaper
from bidi.algorithm import get_display

AMIRI_REGULAR = "/tmp/amiri_fonts/Amiri-1.000/Amiri-Regular.ttf"
AMIRI_BOLD    = "/tmp/amiri_fonts/Amiri-1.000/Amiri-Bold.ttf"
MONO_REGULAR  = "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"
MONO_BOLD     = "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"

BLUE  = (31, 73, 125)
LBLUE = (68, 114, 196)
GRAY  = (89, 89, 89)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
LGRAY = (242, 242, 242)
DBLUE = (17, 52, 86)


def ar(text):
    """Reshape and apply BiDi to Arabic text for correct PDF rendering."""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


class Report(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("Amiri", style="",  fname=AMIRI_REGULAR)
        self.add_font("Amiri", style="B", fname=AMIRI_BOLD)
        self.add_font("Mono",  style="",  fname=MONO_REGULAR)
        self.add_font("Mono",  style="B", fname=MONO_BOLD)
        self.set_auto_page_break(auto=True, margin=20)
        self._page_num = 0

    # ------------------------------------------------------------------ helpers
    def ar_cell(self, w, h, txt, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                border=0, fill=False):
        self.cell(w, h, ar(txt), border=border, align=align,
                  new_x=new_x, new_y=new_y, fill=fill)

    def ar_multi(self, w, txt, align="R"):
        self.multi_cell(w, 7, ar(txt), align=align)

    def section_title(self, title_ar, title_en=""):
        self.ln(4)
        self.set_fill_color(*LBLUE)
        self.set_text_color(*WHITE)
        self.set_font("Amiri", "B", 14)
        label = f"{title_en}  |  {ar(title_ar)}" if title_en else ar(title_ar)
        self.cell(0, 10, label, border=0, align="R", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*BLACK)
        self.ln(3)

    def divider(self):
        self.set_draw_color(*LBLUE)
        self.set_line_width(0.4)
        self.line(self.l_margin, self.get_y(),
                  self.w - self.r_margin, self.get_y())
        self.ln(3)

    # ------------------------------------------------------------------ header/footer
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Amiri", "", 9)
        self.set_text_color(*GRAY)
        self.cell(0, 8, ar("مشروع مادة البرمجة 2 — نظام إدارة مطعم داخل فندق"), align="R",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*LBLUE)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(),
                  self.w - self.r_margin, self.get_y())
        self.ln(2)
        self.set_text_color(*BLACK)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_draw_color(*LBLUE)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(),
                  self.w - self.r_margin, self.get_y())
        self.set_font("Amiri", "", 9)
        self.set_text_color(*GRAY)
        self.cell(0, 8, str(self.page_no()), align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ------------------------------------------------------------------ cover page
    def cover(self):
        self.add_page()

        # top institution block
        self.set_fill_color(*DBLUE)
        self.rect(0, 0, 210, 50, style="F")

        self.set_font("Amiri", "B", 12)
        self.set_text_color(*WHITE)
        self.set_y(6)
        lines = [
            "الجمهورية العربية السورية — وزارة السياحة",
            "الهيئة العامة للتدريب السياحي والفندقي",
            "مركز الوادي للتأهيل والتدريب السياحي والفندقي",
        ]
        for line in lines:
            self.ar_cell(0, 9, line, align="C")

        # decorative stripe
        self.set_fill_color(*LBLUE)
        self.rect(0, 50, 210, 4, style="F")

        # main title block
        self.set_y(70)
        self.set_font("Amiri", "B", 26)
        self.set_text_color(*BLUE)
        self.ar_cell(0, 14, "مشروع مادة البرمجة 2", align="C")

        self.set_font("Amiri", "B", 18)
        self.set_text_color(*DBLUE)
        self.ar_cell(0, 12, "نظام إدارة مطعم داخل فندق", align="C")

        # thin rule
        self.ln(6)
        self.set_draw_color(*LBLUE)
        self.set_line_width(0.8)
        self.line(40, self.get_y(), 170, self.get_y())
        self.ln(10)

        # info block
        info = [
            ("البرنامج الدراسي", "دبلوم في العلوم السياحية"),
            ("الاختصاص", "إدارة سياحية وتطبيقات تقانة معلومات"),
            ("المرحلة", "السنة الأولى — الفصل الثاني"),
            ("اسم الطالبة", "مروة الصحني"),
        ]
        self.set_font("Amiri", "", 14)
        self.set_text_color(*BLACK)
        for label, value in info:
            self.set_x(self.l_margin)
            self.set_font("Amiri", "", 13)
            self.set_text_color(*GRAY)
            self.cell(0, 9, ar(f"{label}:"), align="R",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("Amiri", "B", 14)
            self.set_text_color(*DBLUE)
            self.cell(0, 9, ar(value), align="R",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2)

        # bottom stripe
        self.set_fill_color(*DBLUE)
        self.rect(0, 272, 210, 25, style="F")
        self.set_y(278)
        self.set_font("Amiri", "", 10)
        self.set_text_color(*WHITE)
        self.ar_cell(0, 8, "لغة البرمجة: Java  |  المفاهيم: الوراثة، التجريد، التحميل الزائد، إعادة التعريف", align="C")

    # ------------------------------------------------------------------ TOC
    def toc_page(self):
        self.add_page()
        self.section_title("جدول المحتويات", "Table of Contents")
        entries = [
            ("المقدمة", "Introduction", 3),
            ("فكرة عمل البرنامج", "Program Overview", 3),
            ("الصفوف المستخدمة", "Classes Used", 4),
            ("MenuItem — الصف المجرد", "Abstract MenuItem Class", 4),
            ("Meal — صف الوجبة", "Meal Class", 4),
            ("Drink — صف المشروب", "Drink Class", 4),
            ("Employee — صف الموظف", "Employee Class", 5),
            ("Table — صف الطاولة", "Table Class", 5),
            ("Order — صف الطلب", "Order Class", 5),
            ("Main — الصف الرئيسي", "Main Class", 5),
            ("الكود المصدري الكامل", "Full Source Code", 6),
            ("مثال على تشغيل البرنامج", "Sample Program Run", 10),
        ]
        self.set_font("Amiri", "", 12)
        for ar_title, en_title, page in entries:
            self.set_text_color(*DBLUE)
            self.cell(0, 8,
                      f"{'.' * 60}  {ar(ar_title)}",
                      align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ------------------------------------------------------------------ intro
    def intro_page(self):
        self.add_page()
        self.section_title("المقدمة", "Introduction")
        self.set_font("Amiri", "", 13)
        self.set_text_color(*BLACK)
        intro = (
            "في هذا المشروع قمنا بإنشاء برنامج بلغة Java يهدف إلى إدارة مطعم داخل فندق. "
            "يسمح البرنامج بإدخال بيانات موظف وطاولة، ثم إضافة وجبات ومشروبات إلى طلب الزبون، "
            "وعرض تفاصيل الطلب كاملةً مع الأسعار النهائية. "
            "الهدف من المشروع هو تطبيق المفاهيم الأساسية في البرمجة الكائنية مثل الوراثة، "
            "الصف المجرد، التحميل الزائد للبواني، إعادة تعريف التوابع، والإدخال من المستخدم."
        )
        self.ar_multi(0, intro)
        self.ln(4)

        self.section_title("فكرة عمل البرنامج", "Program Overview")
        overview = (
            "يعتمد البرنامج على مجموعة من الصفوف المترابطة. يقرأ الصف الرئيسي "
            "بيانات الموظف والطاولة من المستخدم، ثم يطلب منه إدخال عدد من العناصر "
            "(وجبات أو مشروبات). بعد الانتهاء يتم إنشاء كائن طلب يحتوي على جميع "
            "البيانات وعرض تفاصيله مع السعر الإجمالي."
        )
        self.ar_multi(0, overview)
        self.ln(4)

        self.section_title("الصفوف المستخدمة في المشروع", "Classes Used")
        classes = [
            ("MenuItem",  "صف مجرد — يمثل أي عنصر في قائمة المطعم (وجبة أو مشروب)"),
            ("Meal",      "يرث من MenuItem — يمثل وجبة مع خاصية الإضافات"),
            ("Drink",     "يرث من MenuItem — يمثل مشروباً بثلاثة أحجام"),
            ("Employee",  "يمثل موظفاً في المطعم — يوضح التحميل الزائد للبواني"),
            ("Table",     "يمثل طاولة في المطعم — يوضح التحميل الزائد للبواني"),
            ("Order",     "يمثل طلب الزبون — يخزن الوجبات والمشروبات في مصفوفة MenuItem[]"),
            ("Main",      "الصف الرئيسي — يقرأ المدخلات ويعرض تفاصيل الطلب"),
        ]
        self.set_font("Amiri", "", 12)
        for cls_name, desc_ar in classes:
            self.set_fill_color(*LGRAY)
            self.set_draw_color(*LBLUE)
            self.set_text_color(*DBLUE)
            self.set_font("Mono", "B", 11)
            self.cell(40, 9, cls_name, border=1, align="L", fill=True,
                      new_x=XPos.RIGHT, new_y=YPos.LAST)
            self.set_font("Amiri", "", 12)
            self.set_text_color(*BLACK)
            self.cell(0, 9, ar(desc_ar), border=1, align="R", fill=False,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ------------------------------------------------------------------ code section
    def code_section(self):
        self.add_page()
        self.section_title("الكود المصدري الكامل", "Full Source Code")

        import os
        files = [
            "MenuItem.java", "Meal.java", "Drink.java",
            "Employee.java", "Table.java", "Order.java", "Main.java",
        ]
        base = "/home/user/sky_scraper/hotel_restaurant"

        for fname in files:
            # file header bar
            self.set_fill_color(*DBLUE)
            self.set_text_color(*WHITE)
            self.set_font("Mono", "B", 11)
            self.cell(0, 8, f"  {fname}", border=0, align="L", fill=True,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            with open(os.path.join(base, fname), encoding="utf-8") as f:
                code = f.read()

            self.set_font("Mono", "", 7.5)
            self.set_text_color(*BLACK)
            self.set_fill_color(*LGRAY)

            # Strip the Arabic header comment — keep only the Java code
            java_start = code.find("public ")
            if java_start == -1:
                java_start = code.find("import ")
            snippet = code[java_start:] if java_start != -1 else code

            for line in snippet.splitlines():
                # color keywords lightly
                stripped = line.rstrip()
                self.set_fill_color(248, 248, 255)
                self.multi_cell(0, 4.5, stripped, border=0, align="L", fill=True,
                                new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            self.ln(4)

    # ------------------------------------------------------------------ sample run
    def sample_run(self):
        self.add_page()
        self.section_title("مثال على تشغيل البرنامج", "Sample Program Run")

        self.set_font("Amiri", "", 12)
        self.set_text_color(*BLACK)
        desc = (
            "عند تشغيل البرنامج يقوم المستخدم بإدخال بيانات الموظف والطاولة، "
            "ثم اختيار عدد العناصر ونوع كل منها. فيما يلي مثال كامل على الإدخال والإخراج:"
        )
        self.ar_multi(0, desc)
        self.ln(3)

        # input/output sample
        sample = """\
Enter employee id: 1
Enter employee name: Ahmad
Enter employee role: Waiter
Enter employee salary: 400

Enter table number: 5
Enter number of seats: 4

Enter number of items in order: 2

Item 1:
Enter item type, 1 for Meal, 2 for Drink: 1
Enter meal id: 101
Enter meal name: Burger
Enter meal price: 5.0
Does the meal have extras? true

Item 2:
Enter item type, 1 for Meal, 2 for Drink: 2
Enter drink id: 201
Enter drink name: Cola
Enter drink price: 1.5
Enter size: Large

Order Details:
Order ID: 1
Table Number: 5
Employee: Ahmad

Items:
Burger - Final Price: 5.75
Cola - Final Price: 1.80
Total Price: 7.55"""

        self.set_fill_color(20, 20, 40)
        self.set_text_color(*WHITE)
        self.set_font("Mono", "", 9)
        self.multi_cell(0, 5.5, sample, border=0, align="L", fill=True,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(6)
        self.section_title("شرح حساب الأسعار النهائية", "Price Calculation Explained")
        self.set_font("Amiri", "", 12)
        self.set_text_color(*BLACK)

        rows = [
            ("العنصر", "السعر الأساسي", "القاعدة", "السعر النهائي"),
            ("Burger (وجبة مع إضافات)", "5.00", "× 1.15  (+15%)", "5.75"),
            ("Cola (مشروب Large)", "1.50", "× 1.20  (+20%)", "1.80"),
            ("الإجمالي", "", "", "7.55"),
        ]
        col_w = [70, 35, 50, 35]
        for i, row in enumerate(rows):
            is_header = (i == 0)
            is_total  = (i == len(rows) - 1)
            self.set_fill_color(*(DBLUE if is_header else (LGRAY if not is_total else LBLUE)))
            self.set_text_color(*(WHITE if (is_header or is_total) else BLACK))
            self.set_font("Amiri", "B" if (is_header or is_total) else "", 11)
            for j, (cell_txt, w) in enumerate(zip(row, col_w)):
                align = "R" if j == 0 else "C"
                if j == 0:
                    self.cell(w, 8, ar(cell_txt), border=1, align=align, fill=True,
                              new_x=XPos.RIGHT, new_y=YPos.LAST)
                else:
                    self.cell(w, 8, cell_txt, border=1, align=align, fill=True,
                              new_x=XPos.RIGHT, new_y=YPos.LAST)
            self.ln(8)

    # ------------------------------------------------------------------ concepts
    def concepts_page(self):
        self.add_page()
        self.section_title("المفاهيم البرمجية المطبّقة", "OOP Concepts Applied")
        self.set_font("Amiri", "", 12)
        self.set_text_color(*BLACK)

        concepts = [
            ("الصف المجرد  (Abstract Class)",
             "تم إنشاء الصف المجرد MenuItem الذي يحتوي على التابع المجرد calculateFinalPrice(). "
             "لا يمكن إنشاء كائن منه مباشرةً، بل يجب أن ترثه الصفوف الأخرى وتنفّذ هذا التابع."),
            ("الوراثة  (Inheritance)",
             "يرث كلٌّ من Meal وDrink من الصف MenuItem باستخدام extends. "
             "يُستخدم super() في بانيهما لاستدعاء بانٍي الصف الأب."),
            ("إعادة تعريف التوابع  (Method Overriding)",
             "يُعيد كلٌّ من Meal وDrink تعريف التابعَين calculateFinalPrice() وdisplayInfo() "
             "ليُناسب طبيعة كل منهما. يُشار إلى ذلك بـ @Override."),
            ("التحميل الزائد للبواني  (Constructor Overloading)",
             "يمتلك كلٌّ من Employee وTable بانيَين: الأول يستقبل جميع البيانات، "
             "والثاني يستقبل بيانات محدودة مع قيم افتراضية."),
            ("تعدد الأشكال  (Polymorphism)",
             "تُخزَّن كائنات Meal وDrink في مصفوفة من نوع MenuItem[] داخل صف Order. "
             "عند استدعاء calculateFinalPrice() يُنفَّذ التابع المناسب لكل كائن تلقائياً."),
            ("محددات الوصول  (Access Modifiers)",
             "تُستخدم protected لمتغيرات MenuItem حتى تستطيع الصفوف الوارثة الوصول إليها، "
             "وprivate لحماية بيانات Employee وTable وOrder وMeal وDrink."),
            ("الإدخال من المستخدم  (Scanner)",
             "يستخدم الصف Main أداة Scanner لقراءة جميع البيانات من المستخدم بشكل تفاعلي."),
        ]

        for title, body in concepts:
            self.set_fill_color(*LGRAY)
            self.set_font("Amiri", "B", 12)
            self.set_text_color(*DBLUE)
            self.cell(0, 8, ar(title), border="B", align="R", fill=True,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("Amiri", "", 11)
            self.set_text_color(*BLACK)
            self.ar_multi(0, body)
            self.ln(3)

    # ------------------------------------------------------------------ class descriptions
    def class_descriptions(self):
        self.add_page()
        self.section_title("وصف الصفوف", "Class Descriptions")

        descs = [
            ("MenuItem.java", "abstract", [
                ("name",  "String",  "protected", "اسم العنصر"),
                ("price", "double",  "protected", "سعر العنصر الأساسي"),
                ("itemId","int",     "protected", "رقم العنصر"),
            ], [
                ("MenuItem(int, String, double)", "باني يستقبل رقم العنصر واسمه وسعره"),
                ("displayInfo()",                 "يعرض معلومات العنصر الأساسية"),
                ("calculateFinalPrice()",          "تابع مجرد — ينفَّذ في الصفوف الوارثة"),
            ]),
            ("Meal.java", "extends MenuItem", [
                ("hasExtras", "boolean", "private", "هل تحتوي الوجبة على إضافات"),
            ], [
                ("Meal(int, String, double, boolean)", "باني الوجبة"),
                ("calculateFinalPrice()",              "يُضيف 15% إذا كانت هناك إضافات"),
                ("displayInfo()",                       "يعرض معلومات الوجبة وحالة الإضافات"),
            ]),
            ("Drink.java", "extends MenuItem", [
                ("size", "String", "private", "حجم المشروب: Small / Medium / Large"),
            ], [
                ("Drink(int, String, double, String)", "باني المشروب"),
                ("calculateFinalPrice()",              "Small: ×1 | Medium: ×1.10 | Large: ×1.20"),
                ("displayInfo()",                       "يعرض معلومات المشروب وحجمه"),
            ]),
            ("Employee.java", "class", [
                ("employeeId", "int",    "private", "رقم الموظف"),
                ("name",       "String", "private", "اسم الموظف"),
                ("role",       "String", "private", "الدور الوظيفي"),
                ("salary",     "double", "private", "الراتب"),
            ], [
                ("Employee(int, String, String, double)", "باني كامل"),
                ("Employee(int, String)",                 "باني مختصر — role=Waiter, salary=300"),
                ("displayEmployeeInfo()",                  "يعرض معلومات الموظف"),
            ]),
            ("Table.java", "class", [
                ("tableNumber",   "int",     "private", "رقم الطاولة"),
                ("numberOfSeats", "int",     "private", "عدد المقاعد"),
                ("isReserved",    "boolean", "private", "حالة الحجز"),
            ], [
                ("Table(int, int, boolean)", "باني كامل"),
                ("Table(int, int)",          "باني مختصر — isReserved=false"),
                ("reserveTable()",           "يغيّر حالة الطاولة إلى محجوزة"),
                ("displayTableInfo()",        "يعرض معلومات الطاولة"),
            ]),
            ("Order.java", "class", [
                ("orderId",    "int",        "private", "رقم الطلب"),
                ("table",      "Table",      "private", "كائن الطاولة"),
                ("employee",   "Employee",   "private", "كائن الموظف"),
                ("items",      "MenuItem[]", "private", "مصفوفة العناصر"),
                ("itemCount",  "int",        "private", "عدد العناصر المضافة"),
            ], [
                ("Order(int, Table, Employee, int)", "باني الطلب"),
                ("addItem(MenuItem)",                "يُضيف عنصراً إلى الطلب"),
                ("calculateTotal()",                 "يحسب مجموع الأسعار النهائية"),
                ("displayOrderDetails()",            "يعرض تفاصيل الطلب كاملة"),
            ]),
        ]

        for cls, modifier, fields, methods in descs:
            # class name bar
            self.set_fill_color(*BLUE)
            self.set_text_color(*WHITE)
            self.set_font("Mono", "B", 11)
            tag = f"  [{modifier}]  {cls}"
            self.cell(0, 8, tag, border=0, align="L", fill=True,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            if fields:
                # fields header
                self.set_fill_color(*DBLUE)
                self.set_text_color(*WHITE)
                self.set_font("Amiri", "B", 10)
                for hdr, w in [("الوصف", 75), ("المحدد", 25), ("النوع", 30), ("الاسم", 60)]:
                    self.cell(w, 7, ar(hdr), border=1, align="C", fill=True,
                              new_x=XPos.RIGHT, new_y=YPos.LAST)
                self.ln(7)
                # field rows
                for fname, ftype, fmod, fdesc in fields:
                    self.set_fill_color(*LGRAY)
                    self.set_text_color(*BLACK)
                    self.set_font("Amiri", "", 10)
                    self.cell(75, 6, ar(fdesc), border=1, align="R", fill=True,
                              new_x=XPos.RIGHT, new_y=YPos.LAST)
                    self.set_font("Mono", "", 9)
                    self.cell(25, 6, fmod, border=1, align="C", fill=False,
                              new_x=XPos.RIGHT, new_y=YPos.LAST)
                    self.cell(30, 6, ftype, border=1, align="C", fill=False,
                              new_x=XPos.RIGHT, new_y=YPos.LAST)
                    self.cell(60, 6, fname, border=1, align="C", fill=False,
                              new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            if methods:
                self.set_fill_color(*LBLUE)
                self.set_text_color(*WHITE)
                self.set_font("Amiri", "B", 10)
                for hdr, w in [("الوصف", 105), ("التابع", 85)]:
                    self.cell(w, 7, ar(hdr), border=1, align="C", fill=True,
                              new_x=XPos.RIGHT, new_y=YPos.LAST)
                self.ln(7)
                for msig, mdesc in methods:
                    self.set_fill_color(240, 245, 255)
                    self.set_text_color(*BLACK)
                    self.set_font("Amiri", "", 10)
                    self.cell(105, 6, ar(mdesc), border=1, align="R", fill=True,
                              new_x=XPos.RIGHT, new_y=YPos.LAST)
                    self.set_font("Mono", "", 8)
                    self.cell(85, 6, msig, border=1, align="L", fill=False,
                              new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            self.ln(5)


# ============================================================ build
def build():
    pdf = Report()
    pdf.cover()
    pdf.toc_page()
    pdf.intro_page()
    pdf.class_descriptions()
    pdf.concepts_page()
    pdf.code_section()
    pdf.sample_run()

    out = "/home/user/sky_scraper/hotel_restaurant/project_report.pdf"
    pdf.output(out)
    print(f"PDF saved: {out}")


if __name__ == "__main__":
    build()
