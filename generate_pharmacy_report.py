"""
PDF report generator for Data Structures project — Pharmacy Hash Table System
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
GREEN = (34, 139, 34)


def ar(text):
    return get_display(arabic_reshaper.reshape(text))


class Report(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("Amiri", style="",  fname=AMIRI_REGULAR)
        self.add_font("Amiri", style="B", fname=AMIRI_BOLD)
        self.add_font("Mono",  style="",  fname=MONO_REGULAR)
        self.add_font("Mono",  style="B", fname=MONO_BOLD)
        self.set_auto_page_break(auto=True, margin=20)

    # ---------------------------------------------------------------- helpers
    def ar_cell(self, w, h, txt, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                border=0, fill=False):
        self.cell(w, h, ar(txt), border=border, align=align,
                  new_x=new_x, new_y=new_y, fill=fill)

    def ar_para(self, w, txt, font="Amiri", size=13, lh=7, align="R"):
        self.set_font(font, "", size)
        avail = w if w > 0 else (self.w - self.l_margin - self.r_margin)
        words = txt.split()
        line_words = []

        def flush():
            if line_words:
                self.cell(avail, lh, ar(" ".join(line_words)), align=align,
                          new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        for word in words:
            trial = " ".join(line_words + [word])
            if self.get_string_width(ar(trial)) <= avail - 2:
                line_words.append(word)
            else:
                flush()
                line_words[:] = [word]
        flush()

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

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Amiri", "", 9)
        self.set_text_color(*GRAY)
        self.cell(0, 8, ar('مشروع بنى المعطيات — نظام الاستعلام الفوري في "صيدلية الوادي"'),
                  align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*LBLUE)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)
        self.set_text_color(*BLACK)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_draw_color(*LBLUE)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_font("Amiri", "", 9)
        self.set_text_color(*GRAY)
        self.cell(0, 8, str(self.page_no()), align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ---------------------------------------------------------------- cover
    def cover(self):
        self.add_page()
        self.set_fill_color(*DBLUE)
        self.rect(0, 0, 210, 50, style="F")
        self.set_font("Amiri", "B", 12)
        self.set_text_color(*WHITE)
        self.set_y(6)
        for line in [
            "وزارة السياحة",
            "مركز الوادي للتأهيل والتدريب السياحي",
            "دبلومة تقانة المعلومات",
        ]:
            self.ar_cell(0, 9, line, align="C")

        self.set_fill_color(*LBLUE)
        self.rect(0, 50, 210, 4, style="F")

        self.set_y(68)
        self.set_font("Amiri", "B", 22)
        self.set_text_color(*BLUE)
        self.ar_cell(0, 13, "مشروع مادة بنى المعطيات", align="C")

        self.set_font("Amiri", "B", 16)
        self.set_text_color(*DBLUE)
        self.ar_cell(0, 11, 'نظام الاستعلام الفوري في "صيدلية الوادي"', align="C")

        self.ln(6)
        self.set_draw_color(*LBLUE)
        self.set_line_width(0.8)
        self.line(40, self.get_y(), 170, self.get_y())
        self.ln(10)

        info = [
            ("البرنامج الدراسي",  "دبلومة تقانة المعلومات"),
            ("بنية البيانات المستخدمة", "Hash Table — جدول التقطيع"),
            ("معالجة التصادم",    "Chaining — السلاسل المتشعبة"),
            ("اسم الطالبة",       "مروة الصحني"),
            ("أستاذ المادة",      "م. زكريا صافي"),
        ]
        self.set_text_color(*BLACK)
        for label, value in info:
            self.set_font("Amiri", "", 12)
            self.set_text_color(*GRAY)
            self.cell(0, 8, ar(f"{label}:"), align="R",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("Amiri", "B", 14)
            self.set_text_color(*DBLUE)
            self.cell(0, 9, ar(value), align="R",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(1)

        self.set_fill_color(*DBLUE)
        self.rect(0, 272, 210, 25, style="F")
        self.set_y(278)
        self.set_font("Amiri", "", 10)
        self.set_text_color(*WHITE)
        self.ar_cell(0, 8,
            "العمليات: إدراج | بحث لحظي | معالجة التصادم | تحديث — لغة البرمجة: Java",
            align="C")

    # ---------------------------------------------------------------- TOC
    def toc_page(self):
        self.add_page()
        self.section_title("جدول المحتويات", "Table of Contents")
        entries = [
            "طرح المشكلة",
            "بنية البيانات المقترحة — Hash Table",
            "دالة التقطيع — Hash Function",
            "معالجة التصادم — Chaining",
            "شرح الدوال المستخدمة",
            "الكود المصدري الكامل",
            "مثال على تشغيل البرنامج",
        ]
        self.set_font("Amiri", "", 12)
        self.set_text_color(*DBLUE)
        for e in entries:
            self.cell(0, 8, f"{'.' * 60}  {ar(e)}",
                      align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ---------------------------------------------------------------- problem
    def problem_page(self):
        self.add_page()
        self.section_title("طرح المشكلة", "Problem Statement")
        self.set_text_color(*BLACK)
        self.ar_para(0,
            'تتعامل صيدلية "الوادي" المركزية مع مئات الآلاف من الأصناف الدوائية، '
            'ويمتلك كل دواء رقم باركود فريد مكون من 4 أرقام. '
            'تعاني الصيدلية حالياً من بطء شديد في عملية البيع؛ لأن النظام الحالي '
            'يبحث عن الدواء عبر فحص السجلات واحداً تلو الآخر (البحث الخطي)، '
            'مما يجعل وقت الانتظار يزداد كلما زاد عدد الأدوية المخزنة.')
        self.ln(4)

        self.section_title("بنية البيانات المقترحة", "Proposed Data Structure")
        self.ar_para(0,
            'الحل الأمثل هو استخدام جدول التقطيع (Hash Table). '
            'هذه البنية تسمح بالوصول المباشر لأي سجل في خطوة زمنية واحدة وثابتة O(1)، '
            'بغض النظر عن حجم البيانات سواء كان في النظام 100 دواء أو مليون دواء. '
            'يتم استخلاص موقع التخزين من رقم الباركود نفسه عبر دالة التقطيع.')
        self.ln(4)

        # comparison table
        self.section_title("مقارنة: البحث الخطي مقابل جدول التقطيع")
        headers = ["جدول التقطيع (الحل)", "البحث الخطي (المشكلة)", "المعيار"]
        widths  = [60, 60, 70]
        rows = [
            ["O(1) — ثابت دائماً", "O(n) — يزيد مع البيانات", "زمن البحث"],
            ["مباشر عبر الباركود", "فحص واحد تلو الآخر", "طريقة الوصول"],
            ["لا يتأثر", "يتباطأ مع الزيادة", "مع نمو البيانات"],
            ["ممتاز", "بطيء جداً", "الأداء في الصيدلية"],
        ]
        self.set_fill_color(*DBLUE)
        self.set_text_color(*WHITE)
        self.set_font("Amiri", "B", 11)
        for h, w in zip(headers, widths):
            self.cell(w, 8, ar(h), border=1, align="C", fill=True,
                      new_x=XPos.RIGHT, new_y=YPos.LAST)
        self.ln(8)
        for row in rows:
            self.set_fill_color(*LGRAY)
            self.set_text_color(*BLACK)
            self.set_font("Amiri", "", 11)
            for i, (cell_txt, w) in enumerate(zip(row, widths)):
                fill = i == 0
                self.set_text_color(*(GREEN if i == 0 else (150, 0, 0) if i == 1 else BLACK))
                self.cell(w, 7, ar(cell_txt), border=1, align="C", fill=fill,
                          new_x=XPos.RIGHT, new_y=YPos.LAST)
            self.ln(7)

    # ---------------------------------------------------------------- functions
    def functions_page(self):
        self.add_page()
        self.section_title("دالة التقطيع — Hash Function")
        self.set_text_color(*BLACK)
        self.ar_para(0,
            'تُستخدم طريقة باقي القسمة (Division Method): '
            'index = barcode % TABLE_SIZE. '
            'حجم الجدول = 1000، وهذا يعني أن باركود 1573 يُخزَّن في الخلية 573، '
            'وباركود 3001 يُخزَّن في الخلية 1، وهكذا.')
        self.ln(3)

        # formula box
        self.set_fill_color(230, 240, 255)
        self.set_draw_color(*LBLUE)
        self.set_font("Mono", "B", 13)
        self.set_text_color(*DBLUE)
        self.cell(0, 10, "  index = barcode % 1000", border=1, align="L", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)

        # examples
        self.set_font("Amiri", "B", 12)
        self.set_text_color(*DBLUE)
        self.ar_cell(0, 8, "أمثلة على دالة التقطيع:")
        examples = [
            ("1573", "1573 % 1000", "573"),
            ("2573", "2573 % 1000", "573  ← تصادم مع 1573"),
            ("3001", "3001 % 1000", "1"),
            ("5000", "5000 % 1000", "0"),
        ]
        self.set_fill_color(*DBLUE)
        self.set_text_color(*WHITE)
        self.set_font("Amiri", "B", 11)
        for h, w in [("الموقع (index)", 70), ("العملية", 70), ("الباركود", 50)]:
            self.cell(w, 7, ar(h), border=1, align="C", fill=True,
                      new_x=XPos.RIGHT, new_y=YPos.LAST)
        self.ln(7)
        for bc, op, idx in examples:
            is_collision = "تصادم" in idx
            self.set_fill_color(255, 240, 240) if is_collision else self.set_fill_color(*LGRAY)
            self.set_text_color(*(150, 0, 0) if is_collision else BLACK)
            self.set_font("Mono", "", 10)
            self.cell(70, 6, ar(idx), border=1, align="C", fill=True,
                      new_x=XPos.RIGHT, new_y=YPos.LAST)
            self.cell(70, 6, op,      border=1, align="C", fill=False,
                      new_x=XPos.RIGHT, new_y=YPos.LAST)
            self.cell(50, 6, bc,      border=1, align="C", fill=False,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)

        self.section_title("معالجة التصادم — Chaining")
        self.ar_para(0,
            'التصادم يحدث عندما يُعطي باركودان مختلفان نفس موقع التخزين. '
            'الحل المستخدم هو السلاسل المتشعبة (Chaining): '
            'كل خلية في الجدول تحتوي على سلسلة مرتبطة (Linked List) '
            'تخزن جميع الأدوية التي تشاركت نفس الموقع. '
            'هذا يضمن عدم ضياع أي سجل دوائي.')
        self.ln(4)

        self.section_title("شرح الدوال المستخدمة", "Function Descriptions")
        funcs = [
            ("hashFunction(barcode)",
             "دالة التقطيع",
             "تحسب موقع التخزين: barcode % 1000. تعمل بزمن O(1) دائماً."),
            ("insert(barcode, name, price)",
             "الإدراج",
             "تضيف دواءاً جديداً عبر حساب موقعه وإدراجه في رأس سلسلة الموقع."),
            ("retrieve(barcode)",
             "البحث اللحظي",
             "تنتقل مباشرةً للموقع ثم تبحث في سلسلته للحصول على الاسم والسعر."),
            ("demonstrateCollision()",
             "معالجة التصادم",
             "توضح عملياً كيف يتعامل النظام مع باركودين يعطيان نفس الموقع."),
            ("update(barcode, newPrice)",
             "التحديث",
             "تنتقل مباشرةً للموقع وتعدّل سعر الدواء دون المرور على بقية العناصر."),
        ]
        for sig, name_ar, desc_ar in funcs:
            self.set_fill_color(*DBLUE)
            self.set_text_color(*WHITE)
            self.set_font("Mono", "B", 10)
            self.cell(0, 7, f"  {sig}", border=0, align="L", fill=True,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("Amiri", "B", 11)
            self.set_text_color(*BLUE)
            self.ar_cell(0, 7, name_ar)
            self.set_font("Amiri", "", 11)
            self.set_text_color(*BLACK)
            self.ar_para(0, desc_ar, size=11, lh=6)
            self.ln(3)

    # ---------------------------------------------------------------- code
    def code_section(self):
        self.add_page()
        self.section_title("الكود المصدري الكامل", "Full Source Code")
        code_path = "/home/user/sky_scraper/pharmacy_system/MarwaAlSahni.java"
        with open(code_path, encoding="utf-8") as f:
            code = f.read()

        self.set_fill_color(*DBLUE)
        self.set_text_color(*WHITE)
        self.set_font("Mono", "B", 10)
        self.cell(0, 7, "  MarwaAlSahni.java", border=0, align="L", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_font("Mono", "", 7.5)
        self.set_text_color(*BLACK)
        for line in code.splitlines():
            self.set_fill_color(248, 248, 255)
            self.multi_cell(0, 4.2, line.rstrip(), border=0, align="L", fill=True,
                            new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ---------------------------------------------------------------- sample run
    def sample_run(self):
        self.add_page()
        self.section_title("مثال على تشغيل البرنامج", "Sample Program Run")
        self.set_text_color(*BLACK)
        self.ar_para(0,
            'فيما يلي مثال كامل يوضح تشغيل البرنامج وإخراجه بعد تنفيذ جميع العمليات الأربع:')
        self.ln(3)

        sample = """\
============================================
 نظام الاستعلام الفوري — صيدلية الوادي
============================================

--- القائمة الرئيسية ---
اختر رقم العملية: 1
رقم الباركود (4 أرقام): 1573
اسم الدواء: Vitamin C
السعر (ل.س): 500
  [+] تمت إضافة الدواء: Vitamin C | موقع التخزين: 573

--- القائمة الرئيسية ---
اختر رقم العملية: 1
رقم الباركود (4 أرقام): 3001
اسم الدواء: Panadol Extra
السعر (ل.س): 350
  [+] تمت إضافة الدواء: Panadol Extra | موقع التخزين: 1

--- القائمة الرئيسية ---
اختر رقم العملية: 2
رقم الباركود: 1573
  [✓] تم العثور على الدواء:
      الاسم  : Vitamin C
      السعر  : 500.0 ل.س

--- القائمة الرئيسية ---
اختر رقم العملية: 3
  باركود 1573 => موقع التخزين: 573
  باركود 2573 => موقع التخزين: 573
  => تصادم! يتم ربطهما في سلسلة بنفس الخلية.
  [+] تمت إضافة الدواء: Paracetamol 500mg | موقع التخزين: 573
  [+] تمت إضافة الدواء: Aspirin 100mg     | موقع التخزين: 573
  => كلا الدواءين محفوظان بدون ضياع أي سجل.

--- القائمة الرئيسية ---
اختر رقم العملية: 4
رقم الباركود: 1573
السعر الجديد (ل.س): 600
  [✓] تم تحديث سعر: Vitamin C
      السعر القديم: 500.0 ل.س
      السعر الجديد: 600.0 ل.س

--- القائمة الرئيسية ---
اختر رقم العملية: 5
  إلى اللقاء!"""

        self.set_fill_color(20, 20, 40)
        self.set_text_color(*WHITE)
        self.set_font("Mono", "", 8.5)
        self.multi_cell(0, 5, sample, border=0, align="L", fill=True,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(5)
        self.section_title("ملاحظة للتشغيل على Windows", "Windows Run Note")
        self.set_text_color(*BLACK)
        self.ar_para(0,
            'لتشغيل البرنامج بشكل صحيح على Windows مع عرض الأرقام بشكل سليم، '
            'استخدم الأمر التالي في terminal برنامج VS Code:')
        self.ln(2)
        self.set_fill_color(230, 240, 255)
        self.set_font("Mono", "B", 11)
        self.set_text_color(*DBLUE)
        self.cell(0, 9, "  chcp 65001  &&  java -Duser.language=en -Duser.country=US MarwaAlSahni",
                  border=1, align="L", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)


# ============================================================ build
def build():
    pdf = Report()
    pdf.cover()
    pdf.toc_page()
    pdf.problem_page()
    pdf.functions_page()
    pdf.code_section()
    pdf.sample_run()

    out = "/home/user/sky_scraper/pharmacy_system/pharmacy_report.pdf"
    pdf.output(out)
    print(f"PDF saved: {out}")


if __name__ == "__main__":
    build()
