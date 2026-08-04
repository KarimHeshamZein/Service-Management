# Arabic UI conventions:
# - Use verbal nouns for control labels (for example: حفظ، تعديل، حذف).
# - Do not use diacritics.
# - Domain terms: مشروع، موقع، جهاز، سجل، خدمة، تركيب/التركيبات، عرض سعر.
# - Preserve product names, file formats, protocols, and technical acronyms literally.
# - Never drop a {placeholder}: it carries real data into the message, and removing
#   it silently destroys that data. test_i18n enforces placeholder parity with en.py.
MESSAGES = {'app.brand.field_service': 'الخدمة الميدانية',
 'app.brand.logo_alt': 'شعار شركة أفاقي',
 'app.brand.service_management': 'إدارة الخدمات',
 'auth.logout': 'تسجيل الخروج',
 'date.month.apr': 'أبريل',
 'date.month.aug': 'أغسطس',
 'date.month.dec': 'ديسمبر',
 'date.month.feb': 'فبراير',
 'date.month.jan': 'يناير',
 'date.month.jul': 'يوليو',
 'date.month.jun': 'يونيو',
 'date.month.mar': 'مارس',
 'date.month.may': 'مايو',
 'date.month.nov': 'نوفمبر',
 'date.month.oct': 'أكتوبر',
 'date.month.sep': 'سبتمبر',
 'language.change': 'تغيير اللغة',
 'language.current': 'اللغة الحالية: {name}',
 'language.label': 'اللغة',
 'login.action.forgot_password': 'نسيت كلمة المرور؟',
 'login.action.submit': 'تسجيل الدخول',
 'login.development_accounts': 'حسابات التطوير',
 'login.field.password': 'كلمة المرور',
 'login.field.username': 'البريد الإلكتروني أو اسم المستخدم',
 'login.hero.description': 'سجل الموقع والخدمة ومن عمل معك والصور التي التقطتها. يوثق النظام اسم '
                           'مقدم السجل ووقت تقديمه.',
 'login.hero.title': 'دليل موثق لأعمال الصيانة التي أنجزتها.',
 'login.modules': 'وحدات التركيبات والصيانة الوقائية والصيانة',
 'login.password_manager_hint': 'يمكن لمتصفحك حفظ كلمة المرور هذه وتعبئتها بأمان.',
 'login.step.evidence': 'أضف الملاحظات والعاملين وصور الإثبات',
 'login.step.finish': 'أكمل أعمال الصيانة في الموقع',
 'login.step.select': 'اختر الموقع والخدمة المنفذة',
 'login.step.submit': 'أرسل السجل — وسيحفظ كإثبات موثق',
 'login.subtitle': 'استخدم الحساب الذي زودك به مسؤول النظام.',
 'login.table.password': 'كلمة المرور',
 'login.table.role': 'الدور',
 'login.table.username': 'اسم المستخدم',
 'login.title': 'تسجيل الدخول',
 'nav.dashboard': 'لوحة المعلومات',
 'nav.group.data_entry': 'إدخال البيانات',
 'nav.group.management': 'الإدارة',
 'nav.group.pricing': 'التسعير',
 'nav.group.records': 'السجلات',
 'nav.group.reports': 'التقارير',
 'nav.installations': 'التركيبات',
 'nav.main': 'التنقل الرئيسي',
 'nav.maintenance': 'الصيانة',
 'nav.management.devices': 'الأجهزة',
 'nav.management.projects': 'المشاريع',
 'nav.management.service_types': 'أنواع الخدمات',
 'nav.management.settings': 'الإعدادات',
 'nav.management.sites': 'المواقع',
 'nav.management.users': 'المستخدمون',
 'nav.open': 'فتح قائمة التنقل',
 'nav.preventive_maintenance': 'الصيانة الوقائية',
 'nav.pricing.items': 'العناصر',
 'nav.pricing.quotations': 'عروض الأسعار',
 'nav.pricing.settings': 'إعدادات التسعير',
 'nav.records.all': 'كل السجلات',
 'nav.records.installation': 'سجلات التركيبات',
 'nav.records.maintenance': 'سجلات الصيانة',
 'nav.records.preventive_maintenance': 'سجلات الصيانة الوقائية',
 'nav.reports.service': 'تقارير الخدمة',
 'nav.reports.technician_activity': 'نشاط الفنيين',
 'photo.stage.after': 'صور بعد العمل',
 'photo.stage.before': 'صور قبل العمل',
 'photo.stage.legacy': 'الإثباتات الحالية',
 'record.label.installation': 'سجل التركيب',
 'record.label.maintenance': 'سجل الصيانة',
 'record.label.preventive_maintenance': 'سجل الصيانة الوقائية',
 'record.device.more': '+{count} أخرى',
 'record.result.completed_successfully': 'اكتمل بنجاح',
 'record.result.completed_with_observations': 'اكتمل مع ملاحظات',
 'record.result.further_action_required': 'يلزم اتخاذ إجراء إضافي',
 'record.result.unable_to_complete': 'تعذر الإكمال',
 'record.type.general_maintenance': 'الصيانة',
 'record.type.installation': 'التركيب',
 'record.type.maintenance': 'الصيانة الوقائية',
 'server.backup.completed': 'اكتمل النسخ الاحتياطي.',
 'server.backup.database.only.completed': 'اكتمل نسخ قاعدة البيانات؛ لقطات الملفات المرفوعة غير '
                                          'مفعلة.',
 'server.backup.database.uploads.completed': 'اكتمل نسخ قاعدة البيانات ولقطة الملفات المرفوعة.',
 'server.backup.disabled': 'النسخ الاحتياطي التلقائي غير مفعل.',
 'server.backup.disabled.summary': 'لن يعمل النسخ الاحتياطي المجدول حتى يتم تفعيله.',
 'server.backup.last.attempt.day': 'كانت آخر محاولة قبل يوم واحد.',
 'server.backup.last.attempt.days': 'كانت آخر محاولة قبل {days} أيام.',
 'server.backup.last.attempt.hour': 'كانت آخر محاولة قبل ساعة واحدة.',
 'server.backup.last.attempt.hours': 'كانت آخر محاولة قبل {hours} ساعات.',
 'server.backup.last.attempt.now': 'كانت آخر محاولة الآن.',
 'server.backup.last.completed.day': 'اكتملت آخر نسخة قبل يوم واحد.',
 'server.backup.last.completed.days': 'اكتملت آخر نسخة قبل {days} أيام.',
 'server.backup.last.completed.hour': 'اكتملت آخر نسخة قبل ساعة واحدة.',
 'server.backup.last.completed.hours': 'اكتملت آخر نسخة قبل {hours} ساعات.',
 'server.backup.last.completed.now': 'اكتملت آخر نسخة الآن.',
 'server.backup.last.success.day': 'اكتملت آخر نسخة احتياطية ناجحة قبل يوم واحد.',
 'server.backup.last.success.days': 'اكتملت آخر نسخة احتياطية ناجحة قبل {days} أيام.',
 'server.backup.last.success.hour': 'اكتملت آخر نسخة احتياطية ناجحة قبل ساعة واحدة.',
 'server.backup.last.success.hours': 'اكتملت آخر نسخة احتياطية ناجحة قبل {hours} ساعات.',
 'server.backup.last.success.now': 'اكتملت آخر نسخة احتياطية ناجحة الآن.',
 'server.backup.latest.failed': 'فشلت آخر محاولة نسخ احتياطي.',
 'server.backup.latest.stale': 'آخر نسخة احتياطية قديمة. تحقق من أن المهمة المجدولة تعمل.',
 'server.backup.prune.warning': 'اكتمل النسخ الاحتياطي، لكن تعذر حذف نسخة قديمة واحدة أو أكثر.',
 'server.backup.status.malformed': 'بيانات حالة النسخ الاحتياطي غير سليمة. تحقق من المهمة '
                                   'المجدولة.',
 'server.backup.status.unavailable': 'لا تتوفر حالة للنسخ الاحتياطي. تحقق من المهمة المجدولة.',
 'server.backup.status.unreadable': 'حالة النسخ الاحتياطي مفقودة أو غير قابلة للقراءة. تحقق من '
                                    'المهمة المجدولة.',
 'server.backup.uploads.complete': 'لقطة كاملة للملفات المرفوعة (وضع {mode}): {path}',
 'server.backup.uploads.disabled': 'لقطات الملفات المرفوعة غير مفعلة. تشمل هذه النسخة قاعدة '
                                   'البيانات فقط، ولن تتضمن الصور عند الاستعادة.',
 'server.catalog.exists': '“{name}” موجود بالفعل.',
 'server.csrf.invalid': 'رمز حماية الجلسة غير صالح',
 'server.device.activated': 'تم تفعيل الجهاز “{name}”.',
 'server.device.added': 'تمت إضافة الجهاز “{name} — {model}”.',
 'server.device.deactivated': 'تم إلغاء تفعيل الجهاز “{name}”.',
 'server.device.deleted': 'تم حذف الجهاز “{name}” نهائيا.',
 'server.device.exists': 'الجهاز “{name} — {model}” موجود بالفعل.',
 'server.device.inactive': 'هذا الجهاز غير نشط.',
 'server.device.invalid': 'أدخل اسما وطرازا صالحين للجهاز.',
 'server.device.limit': 'أضف {maximum} جهازا كحد أقصى إلى السجل الواحد.',
 'server.device.missing': 'هذا الجهاز لم يعد موجودا.',
 'server.device.missing.title': 'هذا الجهاز لم يعد موجودا.',
 'server.device.referenced': 'الجهاز “{name}” مرتبط بالسجل التاريخي، لذلك تم إلغاء تفعيله بدلا من '
                             'حذفه.',
 'server.device.required': 'اسم الجهاز وطرازه مطلوبان.',
 'server.device.select.installation': 'اختر الجهاز الذي يتم تركيبه.',
 'server.device.select.maintenance': 'اختر الجهاز الذي أجريت له الصيانة.',
 'server.device.updated': 'تم تحديث الجهاز “{name}”. تحتفظ السجلات الحالية بلقطاتها.',
 'server.error.access.title': 'ليس لديك صلاحية الوصول',
 'server.error.failed.detail': 'تعذر إكمال الإجراء. حاول مرة أخرى.',
 'server.error.generic.title': 'حدث خطأ',
 'server.error.method.title': 'هذا الإجراء غير متاح هنا',
 'server.error.not_found.detail': 'تحقق من العنوان أو ارجع إلى لوحة المعلومات.',
 'server.error.not_found.title': 'الصفحة غير موجودة',
 'server.error.retry.detail': 'حاول مرة أخرى بعد قليل.',
 # Passthrough, exactly as in en.py. This key carries a message that has no
 # catalog entry of its own; it must keep {message} or the real text is lost.
 'server.fallback': '{message}',
 'server.handover.limit': 'اجعل ملاحظات التسليم أقل من {maximum} حرفا.',
 'server.installation.delete.referenced': 'لا يمكن حذف سجل التركيب لأن أحد أجهزته مرتبط بسجل '
                                          'صيانة.',
 'server.installed.device.inactive': 'الجهاز المركب غير نشط.',
 'server.installed.device.missing': 'الجهاز المركب لم يعد موجودا.',
 'server.installed.device.project': 'اختر جهازا مركبا في هذا المشروع.',
 'server.installed.device.site': 'اختر جهازا مركبا في هذا الموقع.',
 'server.language.unsupported': 'اللغة غير مدعومة.',
 'server.login.account.deactivated': 'هذا الحساب غير نشط. تواصل مع مسؤول النظام.',
 'server.login.failed': 'بيانات الدخول غير صحيحة. تحقق من اسم المستخدم وكلمة المرور.',
 'server.login.password.required': 'أدخل كلمة المرور.',
 'server.login.signed.in': 'تم تسجيل الدخول باسم {name}.',
 'server.login.username.required': 'أدخل بريدك الإلكتروني أو اسم المستخدم.',
 'server.network.adapter.required': 'أدخل اسم محول شبكة LAN في Windows.',
 'server.network.adapter.single': 'أدخل اسم محول Windows واحدا.',
 'server.network.allowed.addresses': 'أدخل عناوين IP أو شبكات صالحة، وافصل بينها بفواصل أو أسطر.',
 'server.network.allowed.required': 'أدخل عناوين IP أو الشبكات البعيدة المسموح لها باستخدام منفذ '
                                    'الاستماع العام.',
 'server.network.dns': 'أدخل عناوين IPv4 صالحة لخوادم DNS، وافصل بينها بفواصل أو أسطر.',
 'server.network.endpoint.distinct': 'يجب أن تختلف نقطة الاتصال العامة عن المحلية.',
 'server.network.ipv4': 'أدخل عنوان IPv4 صالحا.',
 'server.network.port': 'أدخل منفذا من 1 إلى 65535.',
 'server.network.postgres.endpoint': 'لا يمكن لـ PostgreSQL مشاركة منفذ خدمة الويب.',
 'server.network.postgres.host': 'أدخل اسم مضيف PostgreSQL أو عنوان IP صالحا.',
 'server.network.prefix': 'أدخل طول بادئة من 1 إلى 32.',
 'server.notes.installation': 'صف أعمال التركيب التي أكملتها.',
 'server.notes.limit': 'اجعل الملاحظات أقل من {maximum} حرفا.',
 'server.notes.maintenance': 'صف أعمال الصيانة التي نفذتها.',
 'server.number.range': 'أدخل رقما من {minimum} إلى {maximum}.',
 'server.photo.after.limit': 'أرفق 10 صور بعد العمل كحد أقصى.',
 'server.photo.before.limit': 'أرفق 10 صور قبل العمل كحد أقصى.',
 'server.photo.limit': 'أرفق 10 صور كحد أقصى.',
 'server.photo.not_found': 'الصورة غير موجودة',
 'server.photo.required.evidence': 'أرفق صورة إثبات واحدة على الأقل.',
 'server.photo.required.installation': 'أرفق صورة واحدة على الأقل لأعمال التركيب.',
 'server.pricing.company.name.limit': 'يجب ألا يتجاوز اسم الشركة 160 حرفا.',
 'server.pricing.currency.invalid': 'أدخل رمز عملة من ثلاثة أحرف مثل SAR.',
 'server.pricing.default.cost': 'أدخل تكلفة افتراضية صالحة غير سالبة لبند {charge}.',
 'server.pricing.email.invalid': 'أدخل عنوان بريد إلكتروني صالحا للشركة.',
 'server.pricing.image.not_found': 'صورة العنصر غير موجودة.',
 'server.pricing.image.removed': 'تمت إزالة صورة العنصر.',
 'server.pricing.item.activated': 'تم تفعيل عنصر التسعير.',
 'server.pricing.item.deactivated': 'تم إلغاء تفعيل عنصر التسعير.',
 'server.pricing.item.deleted': 'تم حذف عنصر التسعير “{name}”. تحتفظ عروض الأسعار بلقطاتها.',
 'server.pricing.item.invalid': 'أدخل اسم عنصر صالحا وسعرا غير سالب.',
 'server.pricing.item.missing': 'عنصر التسعير هذا لم يعد موجودا.',
 'server.pricing.item.price': 'أدخل سعرا صالحا غير سالب للعنصر.',
 'server.pricing.item.updated': 'تم تحديث عنصر التسعير. تحتفظ عروض الأسعار الحالية بلقطاتها.',
 'server.pricing.main.active': 'اختر عنصرا رئيسيا نشطا.',
 'server.pricing.main.created': 'تم إنشاء العنصر الرئيسي “{name}”.',
 'server.pricing.main.name': 'أدخل اسم العنصر الرئيسي.',
 'server.pricing.phone.limit': 'يجب ألا يتجاوز رقم الهاتف 40 حرفا.',
 'server.pricing.prefix.invalid': 'استخدم حتى 12 حرفا أو رقما أو شرطة.',
 'server.pricing.related.activated': 'تم تفعيل العنصر المرتبط.',
 'server.pricing.related.added': 'تمت إضافة العنصر المرتبط “{name}” إلى “{main}”.',
 'server.pricing.related.deactivated': 'تم إلغاء تفعيل العنصر المرتبط.',
 'server.pricing.related.deleted': 'تم حذف العنصر المرتبط “{name}”. تحتفظ عروض الأسعار بلقطاتها.',
 'server.pricing.related.exists': '“{name}” مرتبط بهذا العنصر بالفعل.',
 'server.pricing.related.invalid': 'أدخل اسم عنصر مرتبط وسعرا صالحا.',
 'server.pricing.related.missing': 'العنصر المرتبط هذا لم يعد موجودا.',
 'server.pricing.related.updated': 'تم تحديث العنصر المرتبط. تحتفظ عروض الأسعار الحالية بلقطاتها.',
 'server.pricing.settings.saved': 'تم حفظ إعدادات التسعير. تحتفظ عروض الأسعار الحالية بلقطاتها.',
 'server.pricing.validity.range': 'أدخل مدة صلاحية من يوم واحد إلى 365 يوما.',
 'server.project.activated': 'تم تفعيل المشروع “{name}”.',
 'server.project.added': 'تمت إضافة المشروع “{name}”.',
 'server.project.deactivated': 'تم إلغاء تفعيل المشروع “{name}”.',
 'server.project.deleted': 'تم حذف المشروع “{name}” نهائيا.',
 'server.project.inactive': 'هذا المشروع غير نشط.',
 'server.project.inactive.records': 'هذا المشروع غير نشط ولا يمكنه استقبال سجلات جديدة.',
 'server.project.missing': 'هذا المشروع لم يعد موجودا.',
 'server.project.missing.title': 'هذا المشروع لم يعد موجودا.',
 'server.project.referenced': 'المشروع “{name}” مرتبط بالسجل التاريخي، لذلك تم إلغاء تفعيله بدلا '
                              'من حذفه.',
 'server.project.required': 'اسم المشروع والعنوان أو الموقع مطلوبان.',
 'server.project.select': 'اختر المشروع.',
 'server.project.updated': 'تم تحديث المشروع “{name}”. تحتفظ السجلات الحالية بتفاصيلها الأصلية.',
 'server.quotation.cost.non_negative': 'أدخل تكلفة صالحة غير سالبة.',
 'server.quotation.created': 'تم إنشاء عرض السعر {number}.',
 'server.quotation.date.invalid': 'أدخل تاريخا صالحا لعرض السعر.',
 'server.quotation.deleted': 'تم حذف عرض السعر {number}.',
 'server.quotation.discount.range': 'أدخل خصما من 0 إلى 100.',
 'server.quotation.duplicate': 'تم إرسال عرض السعر هذا من قبل.',
 'server.quotation.duplicate.list': 'تم إرسال عرض السعر هذا من قبل. راجع قائمة عروض الأسعار.',
 'server.quotation.expiry.invalid': 'أدخل تاريخ انتهاء صالحا.',
 'server.quotation.expiry.order': 'لا يمكن أن يسبق تاريخ الانتهاء تاريخ عرض السعر.',
 'server.quotation.image.not_found': 'صورة عنصر عرض السعر غير موجودة.',
 'server.quotation.item.unique': 'يمكن تحديد كل عنصر رئيسي مرة واحدة.',
 'server.quotation.items.limit': 'يمكن أن يحتوي عرض السعر على 50 عنصرا رئيسيا كحد أقصى.',
 'server.quotation.items.required': 'أضف عنصرا واحدا على الأقل.',
 'server.quotation.not_found': 'عرض السعر غير موجود.',
 'server.quotation.optional.exclusive': 'حدد العناصر الاختيارية أو تخطها، ولا تجمع بين الخيارين.',
 'server.quotation.optional.required': 'حدد عنصرا اختياريا واحدا على الأقل أو حدد تخطي العناصر '
                                       'الاختيارية.',
 'server.quotation.price.non_negative': 'أدخل سعرا صالحا غير سالب.',
 'server.quotation.project.active': 'اختر مشروعا نشطا.',
 'server.quotation.quantity.positive': 'أدخل كمية أكبر من صفر.',
 'server.quotation.related.price': 'أدخل سعرا صالحا لكل عنصر مرتبط محدد.',
 'server.quotation.related.quantity': 'أدخل كمية لكل عنصر مرتبط محدد.',
 'server.quotation.related.unavailable': 'أحد العناصر المرتبطة المحددة غير متاح.',
 'server.quotation.save.failed': 'تعذر حفظ عرض السعر. راجع النموذج وحاول مرة أخرى.',
 'server.quotation.updated': 'تم تحديث عرض السعر {number}.',
 'server.quotation.vat.range': 'أدخل نسبة ضريبة قيمة مضافة من 0 إلى 100.',
 'server.record.deleted': 'تم حذف {record_number} نهائيا.',
 'server.record.device.unique': 'لا يمكن إضافة الجهاز نفسه أكثر من مرة في هذا السجل.',
 'server.record.duplicate.installation': 'تم إرسال سجل التركيب هذا من قبل. راجع قائمة سجلاتك.',
 'server.record.duplicate.maintenance': 'تم إرسال سجل الصيانة هذا من قبل. راجع سجلاتك.',
 'server.record.duplicate.preventive': 'تم إرسال سجل الصيانة الوقائية هذا من قبل. راجع قائمة '
                                       'سجلاتك.',
 'server.record.issue.required': 'صف المشكلة أو الملاحظة المرتبطة بهذه النتيجة.',
 'server.record.no.changes': 'لم يتم إجراء أي تغييرات.',
 'server.record.not_found.installation': 'سجل التركيب غير موجود',
 'server.record.not_found.maintenance': 'سجل الصيانة غير موجود',
 'server.record.not_found.preventive': 'سجل الصيانة الوقائية غير موجود',
 'server.record.project.forbidden': 'هذا السجل خارج المشاريع المعينة لك',
 'server.record.saved.installation': 'تم حفظ سجل التركيب {record_number}.',
 'server.record.saved.maintenance': 'تم حفظ سجل الصيانة {record_number}.',
 'server.record.saved.preventive': 'تم حفظ سجل الصيانة الوقائية {record_number}.',
 'server.record.updated': 'تم تحديث {record_number} وإضافته إلى سجل التغييرات.',
 'server.recovery.email.verified': 'تم توثيق بريد استرداد المسؤول.',
 'server.recovery.generic': 'إذا تطابقت البيانات مع حساب مسؤول موثق، فسيتم إرسال رابط إعادة تعيين '
                            'كلمة المرور.',
 'server.recovery.identifier.required': 'أدخل اسم مستخدم المسؤول أو بريد الاسترداد.',
 'server.recovery.link.invalid': 'رابط إعادة تعيين كلمة المرور غير صالح أو انتهت صلاحيته.',
 'server.recovery.password.length': 'يجب أن تتكون كلمة المرور الجديدة من {minimum} أحرف على الأقل.',
 'server.recovery.password.mismatch': 'كلمتا المرور غير متطابقتين.',
 'server.recovery.password.reset': 'تمت إعادة تعيين كلمة مرور المسؤول. سجل الدخول بكلمة المرور '
                                   'الجديدة.',
 'server.result.installation': 'اختر نتيجة التركيب.',
 'server.result.maintenance': 'اختر نتيجة الصيانة.',
 'server.serial.limit': 'اجعل الرقم التسلسلي أقل من {maximum} حرفا.',
 'server.serial.registered': 'هذا الرقم التسلسلي مسجل من قبل.',
 'server.serial.required': 'أدخل الرقم التسلسلي للجهاز.',
 'server.serial.unique.record': 'يجب ألا يتكرر الرقم التسلسلي داخل هذا السجل.',
 'server.service.activated': 'تم تفعيل الخدمة “{name}”.',
 'server.service.added': 'تمت إضافة الخدمة “{name}”.',
 'server.service.deactivated': 'تم إلغاء تفعيل الخدمة “{name}”.',
 'server.service.inactive': 'هذه الخدمة غير نشطة.',
 'server.service.missing': 'هذه الخدمة لم تعد موجودة.',
 'server.service.name.invalid': 'أدخل اسم خدمة صالحا.',
 'server.service.name.required': 'أدخل اسم الخدمة.',
 'server.service.select': 'اختر الخدمة المنفذة.',
 'server.service.select.installation': 'اختر نوع التركيب.',
 'server.service.type.deleted': 'تم حذف نوع الخدمة “{name}” نهائيا.',
 'server.service.type.missing': 'نوع الخدمة هذا لم يعد موجودا.',
 'server.service.type.referenced': 'نوع الخدمة “{name}” مرتبط بالسجل التاريخي، لذلك تم إلغاء '
                                   'تفعيله بدلا من حذفه.',
 'server.service.updated': 'تم تحديث الخدمة “{name}”. تحتفظ السجلات الحالية باسمها الأصلي.',
 'server.session.expired': 'انتهت صلاحية جلستك. حاول مرة أخرى.',
 'server.session.expired.link': 'انتهت صلاحية جلستك. أعد تحميل الرابط وحاول مرة أخرى.',
 'server.session.expired.reload': 'انتهت صلاحية جلستك. أعد تحميل الصفحة وحاول مرة أخرى.',
 'server.session.expired.reload.short': 'انتهت صلاحية جلستك. أعد التحميل وحاول مرة أخرى.',
 'server.session.expired.short': 'انتهت صلاحية الجلسة.',
 'server.session.expired.submit': 'انتهت صلاحية جلستك. أعد تحميل الصفحة ثم أرسل السجل مرة أخرى.',
 'server.settings.action.unknown': 'إجراء الإعدادات غير معروف.',
 'server.settings.postgres.failed': 'لم يستجب PostgreSQL عند {endpoint}. لم يتم تغيير أي إعدادات.',
 'server.settings.postgres.ok': 'استجاب PostgreSQL عند {endpoint}.',
 'server.settings.save.before.backup': 'احفظ إعدادات النشر قبل تنزيل برنامج النسخ الاحتياطي.',
 'server.settings.save.before.script': 'احفظ إعدادات النشر قبل تنزيل البرنامج.',
 'server.settings.saved': 'تم حفظ إصدار ملف النشر {version}. نزل برنامج تطبيق Windows وشغله لتفعيل '
                          'الإعدادات.',
 'server.settings.script.mode': 'وضع البرنامج غير معروف.',
 'server.site.activated': 'تم تفعيل الموقع “{name}”.',
 'server.site.added': 'تمت إضافة الموقع “{name}”.',
 'server.site.deactivated': 'تم إلغاء تفعيل الموقع “{name}”.',
 'server.site.deleted': 'تم حذف الموقع “{name}” نهائيا.',
 'server.site.inactive': 'هذا الموقع غير نشط.',
 'server.site.inactive.records': 'هذا الموقع غير نشط ولا يمكنه استقبال سجلات جديدة.',
 'server.site.maintenance.select': 'اختر الموقع الذي أجريت فيه الصيانة.',
 'server.site.missing': 'هذا الموقع لم يعد موجودا.',
 'server.site.missing.title': 'هذا الموقع لم يعد موجودا.',
 'server.site.name.invalid': 'أدخل اسم موقع صالحا.',
 'server.site.name.required': 'أدخل اسم الموقع.',
 'server.site.referenced': 'الموقع “{name}” مرتبط بالسجل التاريخي، لذلك تم إلغاء تفعيله بدلا من '
                           'حذفه.',
 'server.site.select': 'اختر الموقع.',
 'server.site.updated': 'تم تحديث الموقع “{name}”. تحتفظ السجلات الحالية باسمه الأصلي.',
 'server.user.activated': 'تم تفعيل حساب {name}.',
 'server.user.admin.created': 'تم إنشاء حساب المسؤول “{name}”.',
 'server.user.customer.created': 'تم إنشاء حساب العميل “{name}”.',
 'server.user.customer.project.required': 'عين مشروعا واحدا على الأقل للعميل.',
 'server.user.deactivated': 'تم إلغاء تفعيل حساب {name}.',
 'server.user.deleted': 'تم حذف المستخدم “{name}” نهائيا.',
 'server.user.identity.required': 'الاسم الكامل والبريد الإلكتروني أو اسم المستخدم مطلوبة.',
 'server.user.missing': 'هذا المستخدم لم يعد موجودا.',
 'server.user.password.length': 'يجب أن تتكون كلمة المرور من {minimum} أحرف على الأقل.',
 'server.user.password.reset': 'تمت إعادة تعيين كلمة مرور {name}.',
 'server.user.project.missing': 'أحد المشاريع المحددة لم يعد موجودا.',
 'server.user.recovery.admin.only': 'بريد الاسترداد متاح لحسابات المسؤولين فقط.',
 'server.user.recovery.invalid': 'أدخل عنوان بريد استرداد صالحا.',
 'server.user.recovery.registered': 'بريد الاسترداد هذا مسجل بالفعل.',
 'server.user.recovery.send.failed': 'تم حفظ بريد الاسترداد، لكن تعذر إرسال رسالة التوثيق. اضبط '
                                     'SMTP ثم أرسلها مرة أخرى.',
 'server.user.recovery.sent': 'تم إرسال رابط التوثيق إلى {email}.',
 'server.user.referenced': 'المستخدم “{name}” مرتبط بالسجلات، لذلك تم إلغاء تفعيله بدلا من حذفه.',
 'server.user.role.invalid': 'اختر نوع مستخدم صالحا.',
 'server.user.role.self': 'لا يمكنك تغيير دور المسؤول لحسابك.',
 'server.user.self.deactivate': 'لا يمكنك إلغاء تفعيل حسابك.',
 'server.user.self.delete': 'لا يمكنك حذف حسابك.',
 'server.user.technical.created': 'تم إنشاء حساب الفني “{name}”.',
 'server.user.updated': 'تم تحديث {name}. تحتفظ السجلات السابقة بالاسم المستخدم عند الإرسال.',
 'server.user.username.taken': 'اسم المستخدم “{username}” مستخدم بالفعل.',
 'server.warranty.invalid': 'أدخل تاريخا صالحا لبدء الضمان.',
 'server.warranty.required': 'اختر تاريخ بدء الضمان.',
 'server.windows.path.absolute': 'أدخل مسار Windows مطلقا.',
 'ui.1.project.name': '1. اسم المشروع',
 'ui.2.site': '2. الموقع',
 'ui.3.quotation.id': '3. معرف عرض السعر',
 'ui.a.database.dump.and.its.same.timestamp.upload.snapshot.form.a.complete': 'يشكل تفريغ قاعدة '
                                                                              'البيانات ولقطة '
                                                                              'التحميل ذات الطابع '
                                                                              'الزمني نفسه زوج '
                                                                              'استعادة كامل.',
 'ui.a.related.item.must.belong.to.an.active.main.item': 'يجب أن ينتمي العنصر ذو الصلة إلى عنصر '
                                                         'رئيسي نشط.',
 'ui.action': 'إجراء',
 'ui.actions': 'الإجراءات',
 'ui.activate': 'تفعيل',
 'ui.activate.on.windows.server': 'التفعيل على خادم Windows',
 'ui.active': 'نشط',
 'ui.add.a.device': 'إضافة جهاز',
 'ui.add.a.main.item': 'إضافة عنصر رئيسي',
 'ui.add.a.project': 'إضافة مشروع',
 'ui.add.a.service': 'إضافة خدمة',
 'ui.add.a.site': 'إضافة موقع',
 'ui.add.a.user': 'إضافة مستخدم',
 'ui.add.add.another.device': '+ إضافة جهاز آخر',
 'ui.add.add.another.installation': '+ إضافة تركيب آخر',
 'ui.add.after.photos': 'إضافة صور بعد العمل',
 'ui.add.an.optional.related.item': 'إضافة عنصر مرتبط اختياري',
 'ui.add.another.main.item': 'إضافة عنصر رئيسي آخر',
 'ui.add.before.photos': 'إضافة صور قبل العمل',
 'ui.add.device': 'إضافة جهاز',
 'ui.add.gate.1.gate.2.gate.3.or.another.site.name': 'أضف بوابة 1، بوابة 2، بوابة 3 أو اسم موقع '
                                                     'آخر.',
 'ui.add.image': 'إضافة صورة',
 'ui.add.main.item': 'إضافة العنصر الرئيسي',
 'ui.add.project': 'إضافة مشروع',
 'ui.add.related.item': 'إضافة عنصر ذي صلة',
 'ui.add.service': 'إضافة خدمة',
 'ui.add.site': 'إضافة موقع',
 'ui.add.the.customer.locations.your.teams.visit': 'أضف مواقع العملاء التي تزورها فرقك.',
 'ui.add.the.device.models.your.teams.install.and.maintain': 'أضف نماذج الأجهزة التي يقوم فريقك '
                                                             'بتركيبها وصيانتها.',
 'ui.add.the.first.project.used.for.installation.and.maintenance.work': 'إضافة المشروع الأول '
                                                                        'المستخدم لأعمال التركيب '
                                                                        'والصيانة.',
 'ui.add.the.services.your.teams.perform.like.camera.service.or.gate.service': 'أضف الخدمات التي '
                                                                               'يؤديها فريقك، مثل '
                                                                               'خدمة الكاميرا أو '
                                                                               'خدمة البوابة.',
 'ui.add.user': 'إضافة مستخدم',
 'ui.additional.access': 'وصول إضافي',
 'ui.address': 'عنوان',
 'ui.address.or.location': 'العنوان أو الموقع',
 'ui.administration': 'إدارة',
 'ui.administrator.audit': 'تدقيق المسؤول',
 'ui.administrator.deployment': 'نشر المسؤول',
 'ui.administrator.password.recovery': 'استعادة كلمة مرور المسؤول ·',
 'ui.administrator.recovery': 'استرداد المسؤول',
 'ui.administrator.recovery.email': 'البريد الإلكتروني لاسترداد المسؤول',
 'ui.administrator.username.or.recovery.email': 'اسم مستخدم المسؤول أو البريد الإلكتروني المخصص '
                                                'للطوارئ',
 'ui.administrators.and.technical.users.can.correct.work.details.every.change.is.recorded': 'يمكن '
                                                                                            'للمسؤولين '
                                                                                            'والمستخدمين '
                                                                                            'الفنيين '
                                                                                            'تصحيح '
                                                                                            'تفاصيل '
                                                                                            'العمل. '
                                                                                            'يتم '
                                                                                            'تسجيل '
                                                                                            'كل '
                                                                                            'تغيير '
                                                                                            'في '
                                                                                            'سجل '
                                                                                            'التدقيق.',
 'ui.administrators.manage.access.technical.users.run.field.operations.and.customers.see.records': 'يقوم '
                                                                                                   'المسؤولون '
                                                                                                   'بإدارة '
                                                                                                   'الوصول، '
                                                                                                   'ويقوم '
                                                                                                   'المستخدمون '
                                                                                                   'الفنيون '
                                                                                                   'بتشغيل '
                                                                                                   'العمليات '
                                                                                                   'الميدانية، '
                                                                                                   'ويرى '
                                                                                                   'العملاء '
                                                                                                   'سجلات '
                                                                                                   'المشاريع '
                                                                                                   'المعينة.',
 'ui.after.photos': 'بعد الصور',
 'ui.all.devices': 'جميع الأجهزة',
 'ui.all.projects': 'جميع المشاريع',
 'ui.all.record.types': 'جميع أنواع السجلات',
 'ui.all.records': 'جميع السجلات ·',
 'ui.all.results': 'جميع النتائج',
 'ui.all.services': 'جميع الخدمات',
 'ui.all.sites': 'جميع المواقع',
 'ui.all.submitted.field.service.evidence.times.shown.in': 'تم تقديم جميع أدلة الخدمة الميدانية. '
                                                           'الأوقات المعروضة في',
 'ui.all.submitters': 'جميع مقدمي الطلبات',
 'ui.all.types': 'جميع الأنواع',
 'ui.and.the.application.restarts': 'ويتم إعادة تشغيل التطبيق.',
 'ui.application': 'التطبيق',
 'ui.applies.to.technical.users.administrators.always.have.pricing.access': 'ينطبق على المستخدمين '
                                                                            'التقنيين. يتمتع '
                                                                            'المسؤولون دائما '
                                                                            'بإمكانية الوصول إلى '
                                                                            'التسعير.',
 'ui.apply.filters': 'تطبيق المرشحات',
 'ui.assign.this.fixed.lan.ip.through.the.windows.apply.script': 'قم بتعيين عنوان IP الثابت للشبكة '
                                                                 'المحلية (LAN) من خلال البرنامج '
                                                                 'النصي لتطبيق Windows',
 'ui.assigned.projects': 'المشاريع المخصصة',
 'ui.at.least.8.characters': 'ما لا يقل عن 8 أحرف',
 'ui.at.least.8.characters.share.it.with.the.user.and.ask.them': 'ما لا يقل عن 8 أحرف. شاركها مع '
                                                                 'المستخدم واطلب منهم الحفاظ على '
                                                                 'خصوصيتها.',
 'ui.audited.edit': '· التحرير المدقق',
 'ui.automatic.postgresql.backups': 'النسخ الاحتياطية التلقائية لـ PostgreSQL',
 'ui.back': 'رجوع',
 'ui.back.to.installations': 'العودة إلى التركيبات',
 'ui.back.to.login': 'العودة لتسجيل الدخول',
 'ui.back.to.records': 'العودة إلى السجلات',
 'ui.backup.directory': 'دليل النسخ الاحتياطي',
 'ui.backups.to.retain': 'النسخ الاحتياطية للاحتفاظ بها',
 'ui.basic.information': 'المعلومات الأساسية',
 'ui.before.photos': 'قبل الصور',
 'ui.browse.all.records': 'تصفح كافة السجلات',
 'ui.by': 'بواسطة',
 'ui.by.lowercase': 'بواسطة',
 'ui.by.service.type': 'حسب نوع الخدمة',
 'ui.by.site': 'حسب الموقع',
 'ui.by.submitter': 'بواسطة المقدم',
 'ui.cancel': 'إلغاء',
 'ui.change.history': 'سجل التغييرات',
 'ui.change.the.period.project.or.record.type': 'قم بتغيير الفترة أو المشروع أو نوع السجل.',
 'ui.change.the.search.or.record.type': 'تغيير نوع البحث أو السجل.',
 'ui.changed.fields': 'الحقول التي تم تغييرها',
 'ui.changes': 'التغييرات',
 'ui.changing.a.network.adapter.can.disconnect.the.server.run.the.apply.script': 'يمكن أن يؤدي '
                                                                                 'تغيير محول '
                                                                                 'الشبكة إلى قطع '
                                                                                 'اتصال الخادم. قم '
                                                                                 'بتشغيل البرنامج '
                                                                                 'النصي للتطبيق من '
                                                                                 'وحدة تحكم '
                                                                                 'Windows Server '
                                                                                 'أو اتصال إدارة '
                                                                                 'آخر باستخدام '
                                                                                 'مسار الاسترداد.',
 'ui.choose.a.main.item': 'اختر عنصرا رئيسيا',
 'ui.choose.a.new.administrator.password': 'اختر كلمة مرور جديدة للمسؤول',
 'ui.choose.a.project': 'اختر مشروعا',
 'ui.choose.a.technician.and.optional.filters.to.review.their.complete.work.history': 'اختر فنيا '
                                                                                      'ومرشحات '
                                                                                      'اختيارية '
                                                                                      'لمراجعة سجل '
                                                                                      'العمل '
                                                                                      'الكامل '
                                                                                      'الخاص بهم.',
 'ui.choose.an.item': 'اختر عنصرا',
 'ui.choose.from.device': 'اختر من الجهاز',
 'ui.city': 'مدينة',
 'ui.clear': 'مسح',
 'ui.clear.filters': 'مسح المرشحات',
 'ui.clear.or.widen.the.filters': 'مسح أو توسيع المرشحات.',
 'ui.close.photo.viewer': 'إغلاق عارض الصور',
 'ui.company.details': 'تفاصيل الشركة',
 'ui.company.name': 'اسم الشركة',
 'ui.completed.successfully': 'تم الانتهاء بنجاح',
 'ui.confirm.new.password': 'تأكيد كلمة المرور الجديدة',
 'ui.contact': 'بيانات الاتصال',
 'ui.contact.number': 'رقم الاتصال',
 'ui.contact.person': 'جهة الاتصال',
 'ui.copied.into.each.new.quotation.and.editable.there': 'منسوخة في كل عرض سعر جديد وقابلة للتحرير '
                                                         'هناك.',
 'ui.create.a.main.item.first': 'قم بإنشاء عنصر رئيسي أولا',
 'ui.create.a.main.item.or.try.a.different.search': 'قم بإنشاء عنصر رئيسي أو حاول إجراء بحث مختلف.',
 'ui.create.and.search.project.quotations.with.fixed.historical.item.and.price.snapshots': 'إنشاء '
                                                                                           'عروض '
                                                                                           'أسعار '
                                                                                           'المشروع '
                                                                                           'والبحث '
                                                                                           'فيها '
                                                                                           'باستخدام '
                                                                                           'العناصر '
                                                                                           'التاريخية '
                                                                                           'الثابتة '
                                                                                           'ولقطات '
                                                                                           'الأسعار.',
 'ui.create.main.item': 'إنشاء العنصر الرئيسي',
 'ui.create.price.quotation': 'إنشاء عرض سعر',
 'ui.create.quotation': 'إنشاء عرض سعر',
 'ui.create.the.first.quotation.or.try.a.different.search': 'قم بإنشاء عرض الأسعار الأول أو حاول '
                                                            'إجراء بحث مختلف.',
 'ui.create.user': 'إنشاء مستخدم',
 'ui.created': 'تم الإنشاء',
 'ui.created.by': 'تم إنشاؤها بواسطة',
 'ui.creates.numbers.such.as.quo.2026.00001': 'إنشاء أرقام مثل QUO-2026-00001.',
 'ui.currency': 'عملة',
 'ui.current.runtime': 'وقت التشغيل الحالي',
 'ui.dashboard': 'لوحة القيادة ·',
 'ui.database': 'قاعدة البيانات',
 'ui.database.user': 'مستخدم قاعدة البيانات',
 'ui.date': 'تاريخ',
 'ui.days': 'أيام',
 'ui.deactivate': 'إلغاء التنشيط',
 'ui.default.terms.and.conditions': 'الشروط والأحكام الافتراضية',
 'ui.default.validity.days': 'الصلاحية الافتراضية (أيام)',
 'ui.default.vat.percent': 'ضريبة القيمة المضافة الافتراضية (%)',
 'ui.delete': 'حذف',
 'ui.delete.quotation': 'حذف عرض السعر',
 'ui.delete.record': 'حذف السجل',
 'ui.delete.this.device.referenced.devices.will.be.deactivated.instead': 'هل تريد حذف هذا الجهاز؟ '
                                                                         'سيتم إلغاء تنشيط الأجهزة '
                                                                         'المشار إليها بدلا من '
                                                                         'ذلك.',
 'ui.delete.this.pricing.item.and.its.related.items.existing.quotations.keep.their': 'هل تريد حذف '
                                                                                     'عنصر التسعير '
                                                                                     'هذا والعناصر '
                                                                                     'المرتبطة به؟ '
                                                                                     'عروض الأسعار '
                                                                                     'الموجودة '
                                                                                     'تحتفظ '
                                                                                     'بلقطاتها.',
 'ui.delete.this.project.referenced.projects.will.be.deactivated.instead': 'هل تريد حذف هذا '
                                                                           'المشروع؟ سيتم إلغاء '
                                                                           'تنشيط المشاريع المشار '
                                                                           'إليها بدلا من ذلك.',
 'ui.delete.this.related.item.existing.quotations.keep.their.snapshots': 'هل تريد حذف هذا العنصر '
                                                                         'ذي الصلة؟ عروض الأسعار '
                                                                         'الموجودة تحتفظ بلقطاتها.',
 'ui.delete.this.service.type.referenced.services.will.be.deactivated.instead': 'هل تريد حذف نوع '
                                                                                'الخدمة هذا؟ سيتم '
                                                                                'إلغاء تنشيط '
                                                                                'الخدمات المشار '
                                                                                'إليها بدلا من '
                                                                                'ذلك.',
 'ui.delete.this.site.referenced.sites.will.be.deactivated.instead': 'هل تريد حذف هذا الموقع؟ سيتم '
                                                                     'إلغاء تنشيط المواقع المشار '
                                                                     'إليها بدلا من ذلك.',
 'ui.delete.this.user.users.referenced.by.records.will.be.deactivated.instead': 'هل تريد حذف هذا '
                                                                                'المستخدم؟ سيتم '
                                                                                'إلغاء تنشيط '
                                                                                'المستخدمين المشار '
                                                                                'إليهم بواسطة '
                                                                                'السجلات بدلا من '
                                                                                'ذلك.',
 'ui.description': 'وصف',
 'ui.detected.server.addresses': 'عناوين الخادم المكتشفة',
 'ui.device': 'جهاز',
 'ui.device.catalog': 'كتالوج الجهاز',
 'ui.device.name': 'اسم الجهاز',
 'ui.device.title': 'جهاز',
 'ui.disabled': 'معطل',
 'ui.devices': 'الأجهزة ·',
 'ui.devices.available.for.new.installations.deactivate.models.instead.of.deleting.them.so': 'الأجهزة '
                                                                                             'المتاحة '
                                                                                             'للتركيبات '
                                                                                             'الجديدة. '
                                                                                             'قم '
                                                                                             'بإلغاء '
                                                                                             'تنشيط '
                                                                                             'النماذج '
                                                                                             'بدلا '
                                                                                             'من '
                                                                                             'حذفها '
                                                                                             'حتى '
                                                                                             'تظل '
                                                                                             'السجلات '
                                                                                             'التاريخية '
                                                                                             'سليمة.',
 'ui.devices.handled': 'الأجهزة التي تم التعامل معها',
 'ui.devices.lowercase': 'الأجهزة',
 'ui.discount': 'تخفيض (',
 'ui.discount.percent': 'تخفيض (٪)',
 'ui.dns.servers': 'خوادم DNS',
 'ui.download.and.run': 'تحميل وتشغيل',
 'ui.download.apply.script': 'تنزيل تطبيق البرنامج النصي',
 'ui.download.backup.task.installer': 'قم بتنزيل أداة تثبيت المهام الاحتياطية',
 'ui.download.pdf': 'تحميل PDF',
 'ui.download.rollback.script': 'تنزيل برنامج التراجع',
 'ui.download.technician.pdf': 'تحميل تقرير الفني PDF',
 'ui.download.the.apply.script.into.the.application.project.root': 'قم بتنزيل البرنامج النصي '
                                                                   'للتطبيق في جذر مشروع التطبيق.',
 'ui.each.item.must.keep.at.least.one.photo.maximum.10.before.and': 'يجب أن يحتفظ كل عنصر بصورة '
                                                                    'واحدة على الأقل. الحد الأقصى '
                                                                    '10 قبل و 10 بعد الصور.',
 'ui.edit': 'تعديل',
 'ui.edit.lowercase': 'تعديل',
 'ui.edit.prefix': 'تعديل ',
 'ui.edit.quotation': 'تحرير عرض السعر',
 'ui.edit.record': 'تحرير السجل',
 'ui.edited': 'تم تحريره',
 'ui.edits': 'التعديلات',
 'ui.email': 'بريد إلكتروني',
 'ui.enable.scheduled.database.backups': 'تمكين النسخ الاحتياطية لقاعدة البيانات المجدولة',
 'ui.enable.the.public.ip.listener': 'تمكين مستمع IP العام',
 'ui.enable.this.only.after.a.reverse.proxy.or.another.tls.endpoint.is': 'قم بتمكين هذا فقط بعد '
                                                                         'تكوين وكيل عكسي أو نقطة '
                                                                         'نهاية TLS أخرى. سيقوم '
                                                                         'التطبيق بوضع علامة على '
                                                                         'ملفات تعريف الارتباط '
                                                                         'الخاصة بالجلسة على أنها '
                                                                         'HTTPS فقط.',
 'ui.enabled': 'مفعل',
 'ui.error': 'خطأ',
 'ui.every.maintenance.and.installation.record.in.one.place': 'سجل كل صيانة وتركيب في مكان واحد.',
 'ui.every.submitted.installation.record': 'كل سجل التركيب المقدم.',
 'ui.every.submitted.maintenance.record': 'كل سجل صيانة مقدم.',
 'ui.every.submitted.preventive.maintenance.record': 'قدم كل سجل صيانة وقائية.',
 'ui.everyone': 'الجميع',
 'ui.evidence.exports': 'تصدير الأدلة',
 'ui.evidence.photos': 'صور الأدلة',
 'ui.existing.photos': 'الصور الموجودة',
 'ui.export': 'تصدير',
 'ui.export.records.for.your.assigned.projects.with.their.work.details.and.evidence': 'قم بتصدير '
                                                                                      'السجلات '
                                                                                      'الخاصة '
                                                                                      'بالمشاريع '
                                                                                      'المخصصة لك '
                                                                                      'مع تفاصيل '
                                                                                      'عملها وصور '
                                                                                      'الأدلة.',
 'ui.field.service': 'الخدمة الميدانية',
 'ui.filter.the.same.service.evidence.shown.in.all.records.then.export.every': 'قم بتصفية نفس دليل '
                                                                               'الخدمة الموضح في '
                                                                               'كافة السجلات، ثم '
                                                                               'قم بتصدير كل تطابق '
                                                                               'مع صوره.',
 'ui.finished.a.visit.file.the.evidence.while.you.are.still.on.site': 'هل أنهيت الزيارة؟ قم بتقديم '
                                                                      'الأدلة أثناء تواجدك في '
                                                                      'الموقع.',
 'ui.fixed.record.identity': 'هوية السجل الثابتة',
 'ui.from': 'من',
 'ui.full.name': 'الاسم الكامل',
 'ui.further.action.required': 'مطلوب مزيد من الإجراءات',
 'ui.go.to.dashboard': 'اذهب إلى لوحة القيادة',
 'ui.grand.total': 'المجموع الإجمالي',
 'ui.handover': 'التسليم:',
 'ui.handover.notes': 'ملاحظات التسليم',
 'ui.hello': 'مرحبا،',
 'ui.http.only.https.can.be.added.in.a.later.release': 'HTTP فقط. يمكن إضافة HTTPS في إصدار لاحق.',
 'ui.image': 'صورة',
 'ui.inactive': 'غير نشط',
 'ui.inactive.with.separator': '· غير نشط',
 'ui.include.evidence.photos': 'تضمين صور الأدلة',
 'ui.include.quotation.id': 'تضمين معرف عرض السعر',
 'ui.include.uploaded.photos.in.a.matching.snapshot': 'قم بتضمين الصور التي تم تحميلها في لقطة '
                                                      'مطابقة',
 'ui.installation': 'تركيب',
 'ui.installation.details': 'تفاصيل التركيب',
 'ui.installation.item': 'عنصر التركيب',
 'ui.installation.notes': 'ملاحظات التركيب',
 'ui.installation.photo': 'صورة التركيب',
 'ui.installation.photo.viewer': 'عارض صور التركيب',
 'ui.installation.photos': 'صور التركيب',
 'ui.installation.price.per.day': 'سعر التركيب باليوم',
 'ui.installation.record.controlled.record': 'سجل التركيب · سجل خاضع للرقابة',
 'ui.installation.records': 'سجلات التركيب ·',
 'ui.installation.records.for.your.assigned.projects': 'سجلات التركيب للمشاريع المخصصة لك.',
 'ui.installation.result': 'نتيجة التركيب',
 'ui.installation.type': 'نوع التركيب',
 'ui.installed': 'تم التركيب',
 'ui.installed.device': 'الجهاز المركب',
 'ui.installed.devices': 'الأجهزة المركبة',
 'ui.internal.application': 'التطبيق الداخلي',
 'ui.internal.application.port': 'منفذ التطبيق الداخلي',
 'ui.invalid.recovery.link': 'رابط الاسترداد غير صالح ·',
 'ui.issue': 'مشكلة:',
 'ui.issue.found': 'تم العثور على مشكلة',
 'ui.item': 'عنصر',
 'ui.item.image': 'صورة السلعة',
 'ui.item.name': 'اسم العنصر',
 'ui.item.title': 'عنصر',
 'ui.items': 'أغراض ·',
 'ui.items.lowercase': 'عناصر',
 'ui.jpeg.png.or.webp.maximum': 'JPEG أو PNG أو WebP. الحد الأقصى',
 'ui.lan.gateway': 'بوابة الشبكة المحلية',
 'ui.lan.ipv4.address': 'عنوان IPv4 للشبكة المحلية',
 'ui.last.updated.by': 'آخر تحديث بواسطة',
 'ui.local.network.access': 'الوصول إلى الشبكة المحلية',
 'ui.local.machine.settings.file.is.unreadable.open.the.service.console': 'ملف إعدادات الجهاز المحلي غير قابل للقراءة. افتح وحدة تحكم الخدمة.',
 'ui.local.service.port': 'منفذ الخدمة المحلية',
 'ui.location': 'مكان',
 'ui.machine.settings.are.read.only.here': 'إعدادات الجهاز للقراءة فقط هنا.',
 'ui.login': 'تسجيل الدخول',
 'ui.main.item': 'العنصر الرئيسي',
 'ui.main.item.details': 'تفاصيل العنصر الرئيسي',
 'ui.maintain.main.items.and.the.optional.priced.items.that.depend.on.them': 'الحفاظ على العناصر '
                                                                             'الرئيسية والأصناف '
                                                                             'المسعرة الاختيارية '
                                                                             'التي تعتمد عليها.',
 'ui.maintained.devices': 'الأجهزة التي تمت صيانتها',
 'ui.maintenance': 'صيانة ·',
 'ui.maintenance.and.installation.records.will.appear.here.after.they.are.submitted': 'ستظهر سجلات '
                                                                                      'الصيانة '
                                                                                      'والتركيب '
                                                                                      'هنا بعد '
                                                                                      'تقديمها.',
 'ui.maintenance.item': 'بند الصيانة',
 'ui.maintenance.notes': 'ملاحظات الصيانة',
 'ui.maintenance.record.controlled.record': 'سجل الصيانة · سجل المراقبة',
 'ui.maintenance.records': 'سجلات الصيانة ·',
 'ui.maintenance.records.for.your.assigned.projects': 'سجلات الصيانة للمشاريع المخصصة لك.',
 'ui.maintenance.result': 'نتيجة الصيانة',
 'ui.manage': 'إدارة',
 'ui.manage.site.names.such.as.gate.1.gate.2.and.gate.3': 'إدارة أسماء المواقع مثل البوابة 1 '
                                                          'والبوابة 2 والبوابة 3.',
 'ui.manage.the.projects.available.for.installation.and.maintenance.data.entry': 'إدارة المشاريع '
                                                                                 'المتاحة لإدخال '
                                                                                 'بيانات التركيب '
                                                                                 'والصيانة.',
 'ui.manpower': 'القوى العاملة',
 'ui.manpower.price.per.worker': 'سعر القوى العاملة لكل عامل',
 'ui.manufacturer': 'الشركة المصنعة',
 'ui.matching.record': 'سجل مطابق',
 'ui.matching.records': 'مطابقة السجلات',
 'ui.model': 'الطراز',
 'ui.more.item': 'المزيد من البند',
 'ui.more.items': 'المزيد من العناصر',
 'ui.name': 'اسم',
 'ui.network.prefix': 'بادئة الشبكة',
 'ui.new.installation': 'تركيب جديد',
 'ui.new.installation.entry': 'إدخال التركيب الجديد',
 'ui.new.installation.with.separator': 'تركيب جديد ·',
 'ui.new.installations': 'التركيبات الجديدة',
 'ui.new.maintenance': 'صيانة جديدة',
 'ui.new.password': 'كلمة المرور الجديدة',
 'ui.new.preventive.maintenance': 'صيانة وقائية جديدة',
 'ui.next': 'التالي',
 'ui.next.photo': 'الصورة التالية',
 'ui.no.activity': 'لا يوجد نشاط.',
 'ui.no.deployment.settings.have.been.saved': 'لم يتم حفظ أي إعدادات نشر.',
 'ui.no.description': 'لا يوجد وصف',
 'ui.no.devices.yet': 'لا توجد أجهزة حتى الآن',
 'ui.no.image': 'لا توجد صورة',
 'ui.no.installation.records.match.those.filters': 'لا توجد سجلات تركيب تتطابق مع تلك المرشحات',
 'ui.no.installation.records.yet': 'لا توجد سجلات التركيب حتى الآن',
 'ui.no.maintenance.records.yet': 'لا توجد سجلات الصيانة حتى الآن',
 'ui.no.non.loopback.ipv4.addresses.were.detected.through.the.application.process': 'لم يتم اكتشاف '
                                                                                    'أي عناوين '
                                                                                    'IPv4 غير '
                                                                                    'قابلة '
                                                                                    'للاسترجاع '
                                                                                    'خلال عملية '
                                                                                    'التطبيق.',
 'ui.no.optional.item.was.included.for.this.main.item': 'لم يتم تضمين أي عنصر اختياري لهذا العنصر '
                                                        'الرئيسي.',
 'ui.no.other.active.technical.users.are.available.this.record.will.show.that': 'لا يتوفر أي '
                                                                                'مستخدمين تقنيين '
                                                                                'نشطين آخرين. '
                                                                                'سيظهر هذا السجل '
                                                                                'أنك عملت بمفردك.',
 'ui.no.photos.are.attached.to.this.record': 'لا توجد صور مرفقة بهذا السجل.',
 'ui.no.photos.attached': 'لا توجد صور مرفقة.',
 'ui.no.photos.yet': 'لا توجد صور بعد',
 'ui.no.preventive.maintenance.records.yet': 'لا توجد سجلات الصيانة الوقائية حتى الآن',
 'ui.no.pricing.items.found': 'لم يتم العثور على عناصر التسعير',
 'ui.no.projects.yet': 'لا توجد مشاريع حتى الآن',
 'ui.no.quotations.found': 'لم يتم العثور على عروض الأسعار',
 'ui.no.records.match.those.filters': 'لا توجد سجلات تتطابق مع عوامل التصفية تلك',
 'ui.no.records.yet': 'لا توجد سجلات حتى الآن',
 'ui.no.related.items.yet': 'لا توجد عناصر ذات صلة حتى الآن.',
 'ui.no.service.types.yet': 'لا توجد أنواع الخدمة حتى الآن',
 'ui.no.sites.match': 'لا توجد مواقع متطابقة "',
 'ui.no.sites.yet': 'لا توجد مواقع حتى الآن',
 'ui.no.submissions.yet': 'لا توجد سجلات مقدمة بعد',
 'ui.no.technician.activity.matches.these.filters': 'لا يوجد أي نشاط فني يتطابق مع عوامل التصفية '
                                                    'هذه',
 'ui.no.users.match': 'لا يوجد مستخدمون مطابقون "',
 'ui.no.value.changes': 'لا توجد تغييرات في القيم',
 'ui.not.verified.send.another.verification.link.if.needed': 'لم يتم التحقق منها. أرسل رابط تحقق '
                                                             'آخر إذا لزم الأمر.',
 'ui.notes': 'ملاحظات',
 'ui.notes.and.findings': 'الملاحظات والنتائج',
 'ui.notes.and.terms': 'الملاحظات والمصطلحات',
 'ui.nothing.matches': 'لا شيء يطابق "',
 'ui.nothing.recorded.yet': 'لم يتم تسجيل أي شيء حتى الآن.',
 'ui.number.of.days.price.per.day': 'عدد الأيام × سعر اليوم الواحد.',
 'ui.number.of.workers.price.per.worker': 'عدد العمال × السعر لكل عامل.',
 'ui.number.project.or.creator': 'رقم أو مشروع أو منشئ...',
 'ui.of': 'من',
 'ui.on': 'على',
 'ui.one.per.line.or.comma.separated.this.field.is.required.when.the': 'واحد لكل سطر أو مفصولة '
                                                                       'بفواصل. هذا الحقل مطلوب '
                                                                       'عند تمكين المستمع العام.',
 'ui.one.transportation.cost.for.this.quotation': 'تكلفة نقل واحدة لعرض السعر هذا.',
 'ui.only.active.sites.appear.in.the.maintenance.form.sites.used.in.records': 'تظهر المواقع النشطة '
                                                                              'فقط في نموذج '
                                                                              'الصيانة. يتم إلغاء '
                                                                              'تنشيط المواقع '
                                                                              'المستخدمة في '
                                                                              'السجلات، ولا يتم '
                                                                              'حذفها مطلقا.',
 'ui.open.installation.photo': 'فتح صورة التركيب',
 'ui.open.the.local.service.console.as.windows.administrator.to.change.machine.settings': 'افتح وحدة تحكم الخدمة المحلية كمسؤول Windows لتغيير إعدادات الجهاز.',
 'ui.open.powershell.on.the.windows.server.using.run.as.administrator': 'افتح PowerShell على خادم '
                                                                        'Windows باستخدام التشغيل '
                                                                        'كمسؤول.',
 'ui.open.proof.photo': 'فتح صورة إثبات',
 'ui.optional.device.details': 'تفاصيل الجهاز الاختيارية',
 'ui.optional.items.skipped': 'تم تخطي العناصر الاختيارية',
 'ui.optional.related.items': 'العناصر الاختيارية ذات الصلة',
 'ui.page': 'صفحة',
 'ui.password.recovery.by.verified.email.is.available.only.for.administrator.accounts': 'استعادة '
                                                                                        'كلمة '
                                                                                        'المرور عن '
                                                                                        'طريق '
                                                                                        'البريد '
                                                                                        'الإلكتروني '
                                                                                        'الذي تم '
                                                                                        'التحقق '
                                                                                        'منه متاح '
                                                                                        'فقط '
                                                                                        'لحسابات '
                                                                                        'المسؤول.',
 'ui.past.records.keep.the.name.used.when.they.were.submitted': 'تحتفظ السجلات السابقة بالاسم '
                                                                'المستخدم عند إرسالها.',
 'ui.pdf.includes.all.matches.and.available.photos': 'يتضمن ملف PDF جميع التطابقات والصور المتوفرة',
 'ui.people.on.site': 'الناس في الموقع',
 'ui.people.who.worked.with.you': 'الأشخاص الذين عملوا معك',
 'ui.permanently.delete.this.installation.record.and.its.photos': 'هل تريد حذف سجل التركيب هذا '
                                                                  'وصوره نهائيا؟',
 'ui.permanently.delete.this.maintenance.record.and.its.photos': 'هل تريد حذف سجل الصيانة هذا '
                                                                 'وصوره نهائيا؟',
 'ui.permanently.delete.this.preventive.maintenance.record.and.its.photos': 'هل تريد حذف سجل '
                                                                            'الصيانة الوقائية '
                                                                            'وصوره نهائيا؟',
 'ui.permanently.delete.this.quotation': 'هل تريد حذف عرض السعر هذا نهائيا؟',
 'ui.permitted.remote.ips.or.networks': 'عناوين IP أو الشبكات البعيدة المسموح بها',
 'ui.pg.dump.executable': 'pg_dump قابل للتنفيذ',
 'ui.phone': 'هاتف',
 'ui.phone.number': 'رقم التليفون',
 'ui.photo': 'صورة',
 'ui.photos': 'صور',
 'ui.photos.lowercase': 'صور',
 'ui.postgresql': 'PostgreSQL',
 'ui.postgresql.connection': 'اتصال PostgreSQL',
 'ui.postgresql.host': 'مضيف PostgreSQL',
 'ui.postgresql.port': 'منفذ PostgreSQL',
 'ui.prefilled.from.items.edit.it.for.this.quotation.only': 'مملوء مسبقا من العناصر. عدله لعرض '
                                                            'السعر هذا فقط.',
 'ui.preventive.maintenance': 'الصيانة الوقائية ·',
 'ui.preventive.maintenance.notes': 'ملاحظات الصيانة الوقائية',
 'ui.preventive.maintenance.record.controlled.record': 'سجل الصيانة الوقائية · سجل المراقبة',
 'ui.preventive.maintenance.records': 'سجلات الصيانة الوقائية ·',
 'ui.preventive.maintenance.records.for.your.assigned.projects': 'سجلات الصيانة الوقائية للمشاريع '
                                                                 'المخصصة لك.',
 'ui.preventive.maintenance.title': 'الصيانة الوقائية',
 'ui.previous': 'سابق',
 'ui.previous.photo': 'الصورة السابقة',
 'ui.price': 'سعر (',
 'ui.price.per.day': 'سعر اليوم(',
 'ui.price.per.worker': 'السعر لكل عامل (',
 'ui.price.quotation': 'عرض أسعار',
 'ui.price.quotations': 'عروض الأسعار ·',
 'ui.priced.items': 'العناصر المسعرة',
 'ui.prices.are.copied.from.the.items.tab.when.you.save': 'يتم نسخ الأسعار من علامة تبويب العناصر '
                                                          'عند الحفظ.',
 'ui.pricing.access': 'الوصول إلى التسعير',
 'ui.pricing.administrator': 'التسعير · المسؤول',
 'ui.pricing.items': 'بنود التسعير',
 'ui.pricing.settings': 'إعدادات التسعير ·',
 'ui.profile.version': 'نسخة الملف الشخصي',
 'ui.project': 'مشروع',
 'ui.project.lowercase': 'مشروع',
 'ui.project.name': 'اسم المشروع',
 'ui.project.record.number.submitter.and.timestamps.remain.unchanged.every.saved.change.is': 'يظل '
                                                                                             'المشروع '
                                                                                             'ورقم '
                                                                                             'السجل '
                                                                                             'والمرسل '
                                                                                             'والطوابع '
                                                                                             'الزمنية '
                                                                                             'دون '
                                                                                             'تغيير. '
                                                                                             'يتم '
                                                                                             'تسجيل '
                                                                                             'كل '
                                                                                             'تغيير '
                                                                                             'محفوظ.',
 'ui.projects': 'المشاريع ·',
 'ui.projects.lowercase': 'المشاريع',
 'ui.proof.photo': 'صورة إثبات',
 'ui.proof.photo.viewer': 'عارض الصور والدليل',
 'ui.proof.photos': 'صور إثبات',
 'ui.proof.photos.on.file': 'صور إثبات في الملف',
 'ui.public.http.access': 'الوصول إلى HTTP العام',
 'ui.public.http.traffic.is.not.encrypted.login.passwords.sessions.records.and.photos': 'حركة مرور '
                                                                                        'HTTP '
                                                                                        'العامة '
                                                                                        'غير '
                                                                                        'مشفرة. '
                                                                                        'يمكن '
                                                                                        'اعتراض '
                                                                                        'كلمات '
                                                                                        'مرور '
                                                                                        'تسجيل '
                                                                                        'الدخول '
                                                                                        'والجلسات '
                                                                                        'والسجلات '
                                                                                        'والصور '
                                                                                        'أثناء '
                                                                                        'النقل. قم '
                                                                                        'بتقييد '
                                                                                        'قاعدة '
                                                                                        'جدار '
                                                                                        'الحماية '
                                                                                        'العامة '
                                                                                        'لعناوين '
                                                                                        'IP '
                                                                                        'البعيدة '
                                                                                        'المعروفة '
                                                                                        'كلما أمكن '
                                                                                        'ذلك.',
 'ui.public.ipv4.address': 'عنوان IPv4 العام',
 'ui.public.service.port': 'ميناء الخدمة العامة',
 'ui.quantity': 'كمية',
 'ui.quotation': 'عرض سعر',
 'ui.quotation.date': 'تاريخ عرض السعر',
 'ui.quotation.defaults': 'الإعدادات الافتراضية لعروض الأسعار',
 'ui.quotation.details': 'تفاصيل عرض السعر',
 'ui.quotation.id': 'معرف عرض السعر',
 'ui.quotation.lowercase': 'عرض سعر',
 'ui.quotation.pages': 'صفحات عرض السعر',
 'ui.quotation.prefix': 'بادئة عرض السعر',
 'ui.quotations': 'عروض الأسعار',
 'ui.recent.submissions': 'التقديمات الأخيرة',
 'ui.recommendation': 'توصية:',
 'ui.recommendations': 'التوصيات',
 'ui.record': 'سجل',
 'ui.record.details': 'تفاصيل السجل',
 'ui.record.edit.history': 'سجل تحرير التاريخ',
 'ui.record.edits': 'سجل التعديلات',
 'ui.record.lowercase': 'سجل',
 'ui.record.number': 'رقم السجل',
 'ui.record.project.site.device': 'سجل، مشروع، موقع، جهاز…',
 'ui.record.project.site.device.notes': 'سجل، مشروع، موقع، جهاز، ملاحظات...',
 'ui.record.site.customer.equipment': 'سجل، موقع، عميل، معدات...',
 'ui.record.site.model.serial': 'سجل، موقع، نموذج، مسلسل...',
 'ui.record.type': 'نوع السجل',
 'ui.recorded': 'مسجلة',
 'ui.records': 'السجلات',
 'ui.records.appear.after.a.maintenance.visit': 'تظهر السجلات بعد زيارة الصيانة.',
 'ui.records.appear.here.after.a.preventive.maintenance.visit': 'تظهر السجلات هنا بعد زيارة '
                                                                'الصيانة الوقائية.',
 'ui.records.appear.here.after.completed.installation.evidence.is.submitted': 'تظهر السجلات هنا '
                                                                              'بعد تقديم أدلة '
                                                                              'التركيب المكتملة.',
 'ui.records.for.your.assigned.projects.in.one.place': 'سجلات المشاريع المخصصة لك في مكان واحد.',
 'ui.recovery.email': 'البريد الإلكتروني للاسترداد',
 'ui.recovery.link.unavailable': 'رابط الاسترداد غير متاح',
 'ui.related.item': 'البند ذو الصلة',
 'ui.related.items': 'العناصر ذات الصلة',
 'ui.remove': 'إزالة',
 'ui.remove.image': 'إزالة الصورة',
 'ui.remove.item': 'إزالة العنصر',
 'ui.renaming.does.not.change.records.already.submitted.for.this.site': 'لا تؤدي إعادة التسمية إلى '
                                                                        'تغيير السجلات التي تم '
                                                                        'إرسالها بالفعل لهذا '
                                                                        'الموقع.',
 'ui.replace.image': 'استبدال الصورة',
 'ui.reports': 'التقارير ·',
 'ui.request.another.link': 'طلب رابط آخر',
 'ui.required.before.forgot.password.can.send.a.reset.link': 'مطلوب قبل أن تتمكن نسيت كلمة المرور '
                                                             'من إرسال رابط إعادة التعيين.',
 'ui.required.charge.defaults': 'الافتراضيات تهمة المطلوبة',
 'ui.required.for.customer.accounts.and.ignored.for.other.roles': 'مطلوب لحسابات العملاء ويتم '
                                                                  'تجاهله للأدوار الأخرى.',
 'ui.required.quotation.charge.per': 'رسوم عرض الأسعار المطلوبة · لكل',
 'ui.required.quotation.charges': 'الرسوم المطلوبة لعرض السعر',
 'ui.resend.verification': 'إعادة إرسال التحقق',
 'ui.reset.administrator.password': 'إعادة تعيين كلمة مرور المسؤول ·',
 'ui.reset.administrator.password.action': 'إعادة تعيين كلمة مرور المسؤول',
 'ui.reset.password': 'إعادة تعيين كلمة المرور',
 'ui.restart.the.application.process.and.test.the.local.endpoint.before.testing.public': 'أعد '
                                                                                         'تشغيل '
                                                                                         'عملية '
                                                                                         'التطبيق '
                                                                                         'واختبر '
                                                                                         'نقطة '
                                                                                         'النهاية '
                                                                                         'المحلية '
                                                                                         'قبل '
                                                                                         'اختبار '
                                                                                         'الوصول '
                                                                                         'العام.',
 'ui.result': 'النتيجة',
 'ui.review.activity': 'مراجعة النشاط',
 'ui.review.work.led.or.assisted.by.a.technical.user.device.outcomes.evidence': 'قم بمراجعة العمل '
                                                                                'الذي يقوده أو '
                                                                                'يساعده مستخدم '
                                                                                'فني، ونتائج '
                                                                                'الجهاز، وإجماليات '
                                                                                'الأدلة، وتحريرات '
                                                                                'السجلات.',
 'ui.revision': 'مراجعة',
 'ui.revisions': 'المراجعات',
 'ui.run': 'تشغيل',
 'ui.run.every.x.days': 'تشغيل كل X أيام',
 'ui.runtime.values.change.only.after.the.windows.script.updates': 'تتغير قيم وقت التشغيل فقط بعد '
                                                                   'تحديث البرنامج النصي لنظام '
                                                                   'التشغيل Windows',
 'ui.save': 'حفظ',
 'ui.save.and.verify.email': 'حفظ والتحقق من البريد الإلكتروني',
 'ui.save.audited.changes': 'حفظ التغييرات التي تم تدقيقها',
 'ui.save.changes': 'حفظ التغييرات',
 'ui.save.device': 'حفظ الجهاز',
 'ui.save.main.item': 'حفظ العنصر الرئيسي',
 'ui.save.pricing.settings': 'حفظ إعدادات التسعير',
 'ui.save.project': 'حفظ المشروع',
 'ui.save.quotation': 'حفظ عرض السعر',
 'ui.save.service': 'حفظ الخدمة',
 'ui.save.site': 'حفظ الموقع',
 'ui.save.staged.settings': 'حفظ الإعدادات المرحلية',
 'ui.saved': 'تم الحفظ',
 'ui.saving': 'جار الحفظ…',
 'ui.saving.installation': 'جار حفظ التركيب…',
 'ui.search': 'بحث',
 'ui.search.devices': 'أجهزة البحث...',
 'ui.search.devices.aria': 'أجهزة البحث',
 'ui.search.name.or.model': 'ابحث عن الاسم أو الطراز...',
 'ui.search.pricing.items': 'البحث عن عناصر التسعير',
 'ui.search.projects': 'مشاريع البحث...',
 'ui.search.projects.aria': 'مشاريع البحث',
 'ui.search.quotations': 'بحث عروض الأسعار',
 'ui.search.services': 'خدمات البحث...',
 'ui.search.services.aria': 'خدمات البحث',
 'ui.search.sites': 'مواقع البحث...',
 'ui.search.sites.aria': 'مواقع البحث',
 'ui.search.users': 'بحث المستخدمين...',
 'ui.search.users.aria': 'بحث المستخدمين',
 'ui.see.all': 'شاهد الكل',
 'ui.select.a.device': 'حدد جهازا',
 'ui.select.a.project': 'اختر مشروعا',
 'ui.select.a.service': 'اختر خدمة',
 'ui.select.a.site': 'اختر موقعا',
 'ui.select.a.technical.user': 'حدد مستخدما تقنيا',
 'ui.select.an.installed.device': 'حدد جهازا مركبا',
 'ui.select.main.items.then.include.only.the.related.items.needed.for.this': 'حدد العناصر '
                                                                             'الرئيسية، ثم قم '
                                                                             'بتضمين العناصر ذات '
                                                                             'الصلة اللازمة لهذا '
                                                                             'المشروع فقط.',
 'ui.select.one.or.more.active.technical.users.leave.empty.if.you.worked': 'حدد واحدا أو أكثر من '
                                                                           'المستخدمين الفنيين '
                                                                           'النشطين. اتركه فارغا '
                                                                           'إذا كنت تعمل بمفردك.',
 'ui.select.technical.users': 'حدد المستخدمين الفنيين',
 'ui.select.the.quotation.created.for.this.project.prices.are.not.shown.here': 'حدد عرض الأسعار '
                                                                               'الذي تم إنشاؤه '
                                                                               'لهذا المشروع. '
                                                                               'الأسعار لا تظهر '
                                                                               'هنا.',
 'ui.select.the.shared.location.then.add.every.device.installed.during.this.visit': 'حدد الموقع '
                                                                                    'المشترك، ثم '
                                                                                    'قم بإضافة كل '
                                                                                    'جهاز تم '
                                                                                    'تركيبه أثناء '
                                                                                    'هذه الزيارة.',
 'ui.select.the.shared.location.then.add.every.device.maintained.during.this.visit': 'حدد الموقع '
                                                                                     'المشترك، ثم '
                                                                                     'قم بإضافة كل '
                                                                                     'جهاز تمت '
                                                                                     'صيانته أثناء '
                                                                                     'هذه الزيارة.',
 'ui.send.reset.link': 'إرسال رابط إعادة التعيين',
 'ui.serial.number': 'رقم سري',
 'ui.service': 'خدمة',
 'ui.service.evidence': 'أدلة الخدمة',
 'ui.service.lowercase': 'خدمة',
 'ui.service.name': 'اسم الخدمة',
 'ui.service.performed': 'تم تنفيذ الخدمة',
 'ui.service.records.appear.after.submission': 'ستظهر سجلات الخدمة هنا فور تقديمها.',
 'ui.service.types': 'أنواع الخدمة ·',
 'ui.services': 'خدمات',
 'ui.set.by.the.administrator.in.pricing.settings': 'يتم تعيينها بواسطة المسؤول في إعدادات '
                                                    'التسعير.',
 'ui.set.quotation.defaults.and.the.company.details.printed.on.future.pdfs': 'قم بتعيين الإعدادات '
                                                                             'الافتراضية لعروض '
                                                                             'الأسعار وتفاصيل '
                                                                             'الشركة المطبوعة على '
                                                                             'ملفات PDF '
                                                                             'المستقبلية.',
 'ui.settings': 'إعدادات ·',
 'ui.settings.audit': 'تدقيق الإعدادات',
 'ui.shared.location': 'الموقع المشترك',
 'ui.sim.card.transportation.engraving': 'بطاقة SIM، النقل، النقش…',
 'ui.site': 'موقع',
 'ui.site.lowercase': 'موقع',
 'ui.site.name': 'اسم الموقع',
 'ui.sites': 'المواقع ·',
 'ui.sites.lowercase': 'المواقع',
 'ui.smtp.is.not.configured.on.this.server': 'لم يتم تكوين SMTP على هذا الخادم.',
 'ui.stage.the.windows.server.ip.port.and.postgresql.connection.settings.used.for': 'قم بإعداد '
                                                                                    'إعدادات '
                                                                                    'Windows '
                                                                                    'Server IP '
                                                                                    'والمنفذ '
                                                                                    'واتصال '
                                                                                    'PostgreSQL '
                                                                                    'المستخدمة '
                                                                                    'للوصول إلى '
                                                                                    'HTTP العام '
                                                                                    'والمحلي.',
 'ui.status': 'حالة',
 'ui.submit.installation.record': 'إرسال سجل التركيب',
 'ui.submit.maintenance.record': 'تقديم سجل الصيانة',
 'ui.submit.preventive.maintenance.record': 'تقديم سجل الصيانة الوقائية',
 'ui.submitted': 'تم التقديم',
 'ui.submitted.by': 'مقدم من',
 'ui.submitted.from': 'تاريخ التقديم من',
 'ui.submitted.maintenance.and.installation.records.will.appear.here': 'ستظهر هنا سجلات الصيانة '
                                                                       'والتركيب المقدمة.',
 'ui.submitted.to': 'مقدم إلى',
 'ui.submitted.today': 'قدمت اليوم',
 'ui.subtotal': 'المجموع الفرعي',
 'ui.take.a.photo': 'التقاط صورة',
 'ui.technical.and.customer.passwords.can.only.be.reset.by.a.logged.in': 'لا يمكن إعادة تعيين '
                                                                         'كلمات المرور الفنية '
                                                                         'وكلمات المرور الخاصة '
                                                                         'بالعملاء إلا بواسطة '
                                                                         'مسؤول مسجل الدخول.',
 'ui.technical.user': 'المستخدم الفني',
 'ui.technician.activity': 'النشاط الفني ·',
 'ui.terms.and.conditions': 'الشروط والأحكام',
 'ui.test.postgresql': 'اختبار PostgreSQL',
 'ui.the.application.binds.to.127.0.0.1.on.this.port.windows': 'يرتبط التطبيق بـ 127.0.0.1 على هذا '
                                                               'المنفذ. يقوم Windows بإعادة توجيه '
                                                               'كلا نقطتي النهاية الخارجية هنا.',
 'ui.the.apply.script.verifies.that.the.public.ip.is.assigned.to.windows': 'يتحقق البرنامج النصي '
                                                                           'للتطبيق من تعيين عنوان '
                                                                           'IP العام لنظام التشغيل '
                                                                           'Windows قبل إنشاء '
                                                                           'المستمع العام.',
 'ui.the.downloaded.installer.creates.a.windows.scheduled.task.running.at.02.00': 'تنشئ أداة '
                                                                                  'التثبيت التي تم '
                                                                                  'تنزيلها مهمة '
                                                                                  'مجدولة لنظام '
                                                                                  'التشغيل Windows '
                                                                                  'تعمل في الساعة '
                                                                                  '02:00 كل فاصل '
                                                                                  'زمني تم تكوينه. '
                                                                                  'تحتوي عمليات '
                                                                                  'تفريغ قاعدة '
                                                                                  'البيانات ولقطات '
                                                                                  'التحميل على '
                                                                                  'حدود احتفاظ '
                                                                                  'مستقلة.',
 'ui.the.list.technical.users.pick.from.deactivate.a.service.instead.of.deleting': 'القائمة التي '
                                                                                   'يختار منها '
                                                                                   'المستخدمون '
                                                                                   'الفنيون. قم '
                                                                                   'بإلغاء تنشيط '
                                                                                   'الخدمة بدلا من '
                                                                                   'حذفها حتى '
                                                                                   'تحتفظ السجلات '
                                                                                   'القديمة باسم '
                                                                                   'الخدمة الأصلي '
                                                                                   'الخاص بها.',
 'ui.the.old.password.stops.working.immediately': 'كلمة المرور القديمة تتوقف عن العمل على الفور.',
 'ui.the.pdf.always.includes.the.full.filtered.ledger.and.device.notes': 'يتضمن ملف PDF دائما دفتر '
                                                                         'الأستاذ الذي تمت تصفيته '
                                                                         'بالكامل وملاحظات الجهاز.',
 'ui.the.related.item.appears.only.when.this.main.item.is.selected.on': 'يظهر العنصر ذو الصلة فقط '
                                                                        'عند تحديد هذا العنصر '
                                                                        'الرئيسي في عرض الأسعار.',
 'ui.these.prefill.new.quotations.the.quotation.creator.can.change.every.cost': 'تملأ هذه القيم '
                                                                                'عروض الأسعار '
                                                                                'الجديدة مسبقا. '
                                                                                'يمكن لمنشئ عرض '
                                                                                'السعر تغيير كل '
                                                                                'تكلفة.',
 'ui.these.three.charges.appear.on.every.quotation.and.cannot.be.removed': 'تظهر هذه الرسوم '
                                                                           'الثلاثة في كل عرض '
                                                                           'أسعار ولا يمكن '
                                                                           'إزالتها.',
 'ui.this.changes.the.application.s.connection.target.postgresql.must.already.be.listening': 'يؤدي '
                                                                                             'هذا '
                                                                                             'إلى '
                                                                                             'تغيير '
                                                                                             'هدف '
                                                                                             'اتصال '
                                                                                             'التطبيق. '
                                                                                             'يجب '
                                                                                             'أن '
                                                                                             'يكون '
                                                                                             'PostgreSQL '
                                                                                             'يستمع '
                                                                                             'بالفعل '
                                                                                             'على '
                                                                                             'هذا '
                                                                                             'المضيف '
                                                                                             'والمنفذ. '
                                                                                             'تظل '
                                                                                             'كلمة '
                                                                                             'مرور '
                                                                                             'قاعدة '
                                                                                             'البيانات '
                                                                                             'موجودة '
                                                                                             'فقط',
 'ui.this.password.reset.link.is.invalid.or.has.expired': 'رابط إعادة تعيين كلمة المرور هذا غير '
                                                          'صالح أو انتهت صلاحيته.',
 'ui.this.recovery.link.is.invalid.or.has.expired': 'رابط الاسترداد هذا غير صالح أو انتهت صلاحيته.',
 'ui.this.technician.made.no.record.edits.in.the.selected.period': 'لم يقم هذا الفني بإجراء أي '
                                                                   'تعديلات على السجل خلال الفترة '
                                                                   'المحددة.',
 'ui.times.in': 'الأوقات في',
 'ui.to': 'إلى',
 'ui.to.apply.the.backup.schedule': 'لتطبيق جدول النسخ الاحتياطي.',
 'ui.total': 'المجموع',
 'ui.total.records': 'إجمالي السجلات',
 'ui.total.visits': 'إجمالي الزيارات',
 'ui.totals': 'الإجماليات',
 'ui.transportation': 'مواصلات',
 'ui.transportation.cost': 'تكلفة النقل (',
 'ui.transportation.cost.label': 'تكلفة النقل',
 'ui.try.a.different.name.or.login': 'جرب اسما مختلفا أو قم بتسجيل الدخول.',
 'ui.type': 'النوع',
 'ui.unable.to.complete': 'غير قادر على الإكمال',
 'ui.unit.price': 'سعر الوحدة (',
 'ui.unit.price.label': 'سعر الوحدة',
 'ui.updated': 'تم التحديث',
 'ui.upload.snapshots.to.retain': 'تحميل لقطات للاحتفاظ بها',
 'ui.use.https.at.the.tls.termination.endpoint': 'استخدم HTTPS عند نقطة نهاية إنهاء TLS',
 'ui.use.the.same.port.for.public.local.and.internal.access': 'استخدم المنفذ نفسه للوصول العام والمحلي والداخلي.',
 'ui.user': 'مستخدم',
 'ui.user.type': 'نوع المستخدم',
 'ui.users': 'المستخدمون ·',
 'ui.users.lowercase': 'المستخدمين',
 'ui.valid.until': '· صالحة حتى',
 'ui.valid.until.label': 'صالحة حتى',
 'ui.vat': 'ضريبة القيمة المضافة (',
 'ui.vat.percent': 'ضريبة القيمة المضافة (%)',
 'ui.verified': 'تم التحقق منه',
 'ui.version': 'إصدار',
 'ui.view': 'عرض',
 'ui.view.details': 'عرض التفاصيل',
 'ui.visit': 'زيارة',
 'ui.visits': 'الزيارات',
 'ui.visits.assisted': 'الزيارات ساعدت',
 'ui.visits.led': 'أدت الزيارات',
 'ui.warranty.start': 'بداية الضمان',
 'ui.was.saved.by': 'تم حفظه بواسطة',
 'ui.what.this.service.covers': 'ما تغطيه هذه الخدمة.',
 'ui.who.was.on.site': 'من كان في الموقع',
 'ui.widen.the.filters.or.clear.them.to.see.everything': 'قم بتوسيع عوامل التصفية أو مسحها لرؤية '
                                                         'كل شيء.',
 'ui.widen.the.search.or.clear.the.filters': 'قم بتوسيع البحث أو مسح عوامل التصفية.',
 'ui.windows.lan.adapter.name': 'اسم محول Windows LAN',
 'ui.with.observations': 'مع الملاحظات',
 'ui.work.history': 'تاريخ العمل',
 'ui.worked.alone': 'عملت وحدها.',
 'ui.worked.with': 'عملت مع',
 'ui.workers': 'العمال',
 'ui.your.recent.submissions': 'أحدث مشاركاتك',
 'ui.your.records': 'السجلات الخاصة بك',
 'ui.available': 'متاح',
 'ui.add.another.item': 'إضافة عنصر آخر',
 'ui.available.for.service.records': 'متاح لسجلات الخدمة',
 'ui.calculated.from.manpower': 'محسوب من تكلفة العمالة',
 'ui.installed.item': 'العنصر المركب',
 'ui.not.available': 'غير متاح',
 'ui.service.records': 'سجلات الخدمة',
 'ui.select.an.installed.item': 'اختر عنصرا مركبا',
 'ui.select.the.shared.location.then.add.every.item.installed.during.this.visit': 'اختر الموقع المشترك، ثم أضف كل عنصر تم تركيبه خلال هذه الزيارة.',
 'ui.select.the.shared.location.then.add.every.item.maintained.during.this.visit': 'اختر الموقع المشترك، ثم أضف كل عنصر تمت صيانته خلال هذه الزيارة.',
 'user.role.admin': 'مسؤول النظام',
 'user.role.customer': 'عميل',
 'user.role.technical': 'فني'}
