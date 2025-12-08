# BytenekoProyect/core/admin.py
from django.contrib import admin
from .models import Plan, Subscription, UserProfile

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'price_monthly', 'max_surveys', 'includes_advanced_analysis')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('price_monthly', 'max_surveys')

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'current_period_end')
    list_filter = ('status', 'plan')
    search_fields = ('user__username', 'user__email')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'company_name', 'phone_number')