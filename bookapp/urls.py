from django.urls import path
from .views import UploadUniversalBookView,  SearchInBookView

urlpatterns = [
    path('books/', UploadUniversalBookView.as_view(), name='upload-book'),
    path("books/<int:book_id>/", UploadUniversalBookView.as_view()),  # for DELETE with book_id in path
    path("generate-questions/", SearchInBookView.as_view(), name="search-in-book"),
]


