from django.db import models

class Book(models.Model):
    title = models.CharField(max_length=200)
    subject = models.CharField(max_length=100)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='books/')

    def __str__(self):
        return self.title
