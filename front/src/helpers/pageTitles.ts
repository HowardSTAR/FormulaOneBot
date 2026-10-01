export const pageTitles: Record<string, string> = {
  '/': 'Обзор', '/account': 'Аккаунт', '/compare': 'Сравнение', '/prediction-analytics': 'Аналитика предсказаний',
  '/constructor-details': 'Карточка команды', '/team-principal': 'Руководитель команды', '/constructors': 'Кубок конструкторов',
  '/driver-details': 'Карточка пилота', '/drivers': 'Личный зачёт', '/history': 'История чемпионата', '/community': 'С друзьями',
  '/favorites': 'Избранное', '/next-race': 'Следующая гонка', '/quali-results': 'Квалификация', '/race-details': 'Гран-при',
  '/race-results': 'Результаты гонки', '/reaction-game': 'Тест реакции', '/reflex-grid-game': 'Reflex Grid', '/race-game': 'Emerald Loop',
  '/predictions': 'Прогнозы', '/practice-results': 'Свободные заезды', '/contact-admin': 'Обратная связь', '/reset-password': 'Сброс пароля',
  '/settings': 'Настройки', '/season': 'Календарь', '/sprint-quali-results': 'Спринт-квалификация', '/sprint-results': 'Спринт',
  '/voting': 'Голосование', '/wiki': 'Справочник F1', '/notifications': 'Уведомления', '/privacy': 'Конфиденциальность',
  '/terms': 'Условия использования', '/legal/ip': 'Интеллектуальная собственность', '/about/data': 'Источники данных',
  '/account/delete': 'Удаление данных', '/admin': 'Админ-панель', '/legal/notices': 'Сторонние компоненты', '/legal/assets': 'Реестр материалов',
};
export function pageTitle(path: string) { return `${path.startsWith('/share/') ? 'Карточка участника' : pageTitles[path] || 'Страница не найдена'} · F1Hub — проект TurboTears`; }
