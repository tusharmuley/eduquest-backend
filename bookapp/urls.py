from django.urls import path
from .views import UploadBookView,  SearchInBookView

urlpatterns = [
    path('books/', UploadBookView.as_view(), name='upload-book'),
     path("books/<int:book_id>/", UploadBookView.as_view()),  # for DELETE with book_id in path
    path("generate-questions/", SearchInBookView.as_view(), name="search-in-book"),
]


