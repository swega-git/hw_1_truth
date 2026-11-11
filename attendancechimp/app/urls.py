from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='home'),
    path('index.html', views.index, name='index_html'),
    path('time', views.time_view, name='time'),
    path('sum', views.sum_view, name='sum'),
    path('new', views.new, name='new'),
    path('createUser', views.createUser, name='createUser'),
    path("new_course", views.new_course, name="new_course"),
    path("createCourse", views.createCourse, name="createCourse"),
    path("new_lecture", views.new_lecture, name="new_lecture"),
    path("createLecture", views.createLecture, name="createLecture"),
    path("new_qr_upload", views.new_qr_upload, name="new_qr_upload"),
    path("createQRCodeUpload", views.createQRCodeUpload, name="createQRCodeUpload"),
    path("dumpUploads", views.dumpUploads, name="dumpUploads"),
]
