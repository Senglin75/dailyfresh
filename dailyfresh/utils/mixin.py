from django.contrib.auth.decorators import login_required


class LoginRequiredMixin(object):
    @classmethod
    def as_view(cls, **initkeywords):
        view = super(LoginRequiredMixin, cls).as_view(**initkeywords)
        return login_required(view)  # 实际上返回的是 login_required(as_view()) 方法
