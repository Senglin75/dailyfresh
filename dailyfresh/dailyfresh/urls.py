"""dailyfresh URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.8/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Add a URL to urlpatterns:  url(r'^blog/', include(blog_urls))
"""
from django.conf.urls import include, url
from django.contrib import admin

urlpatterns = [
    url(r'^admin/', include(admin.site.urls)),
    url(r'^tinymce/', include('tinymce.urls')),  # 配置富文本 url
    url(r'^search/', include('haystack.urls')),  # 设置全文检索 url
    url(r'^user/', include('user.urls', namespace='user')),  # namespace 反向解析,根据用户的输入动态的生成 url
    url(r'^cart/', include('cart.urls', namespace='cart')),
    url(r'^order/', include('order.urls', namespace='order')),
    url(r'^', include('goods.urls', namespace='goods'))  # 商品模块的 url 放置最后,防止在匹配其他模块 url 时,因为 url 是顺序匹配,而一直匹配到 goods 首页
]
