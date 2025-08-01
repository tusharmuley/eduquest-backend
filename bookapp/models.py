from django.db import models

# models.py
class Book(models.Model):
    BOOK_TYPE_CHOICES = [
        ('text', 'Text'),
        ('structured', 'Structured')
    ]

    title = models.CharField(max_length=200)
    subject = models.CharField(max_length=100 , null=True, blank=True)  # ✅ Added subject field
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='books/')
    type = models.CharField(max_length=20, choices=BOOK_TYPE_CHOICES, default='text')  # <-- ✅ default added

    def __str__(self):
        return self.title
    
    
    
class BookStructuredData(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    sheet_name = models.CharField(max_length=100, default="Sheet1")  # ✅ NEW COLUMN
    row_index = models.IntegerField()
    column_name = models.TextField()
    value = models.TextField()

    def __str__(self):
        return f"{self.book.title} | Row {self.row_index} | {self.column_name}"
