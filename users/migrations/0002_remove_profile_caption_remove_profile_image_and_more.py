# Generated by Django 5.1.2 on 2024-10-16 14:06

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='profile',
            name='caption',
        ),
        migrations.RemoveField(
            model_name='profile',
            name='image',
        ),
        migrations.RemoveField(
            model_name='profile',
            name='upload_date',
        ),
        migrations.RemoveField(
            model_name='profile',
            name='video',
        ),
        migrations.CreateModel(
            name='Upload',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(blank=True, null=True, upload_to='profile_pics')),
                ('video', models.FileField(blank=True, null=True, upload_to='profile_videos')),
                ('caption', models.TextField(blank=True)),
                ('upload_date', models.DateTimeField(auto_now_add=True)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='uploads', to='users.profile')),
            ],
        ),
    ]
