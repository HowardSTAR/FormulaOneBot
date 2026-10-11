export type ProfileGuideStatus = 'completed' | 'skipped';
export const PROFILE_GUIDE_START = 'turbotears:profile-guide-start';
const session = new Map<number,ProfileGuideStatus>();
const key = (userId: number) => `turbotears-profile-guide-v1:${userId}`;

export const profileGuideSteps = [
  { target: '.profile-avatar-control', title: 'Твой образ', text: 'Нажми на аватар или «Аватар и оформление»: выбери шлем, комбинезон и фон. Здесь же доступны рамки и цвет имени.' },
  { target: '#profile-trophies', title: 'Твоя коллекция', text: 'Прогнозы и игры открывают бронзовые, серебряные и золотые трофеи. Нажми на медаль, изучи условие и выбери любой полученный уровень бейджем рядом с именем.' },
  { target: '.profile-season', title: 'Сезон в цифрах', text: 'Переключай сезон, чтобы посмотреть свои очки, рассчитанные прогнозы и лучший результат. Сезонные трофеи считают участие отдельно за каждый год.' },
  { target: '[data-profile-guide="predictions"]', title: 'Твои прогнозы', text: 'Раскрой этап, чтобы увидеть ответы и баллы. Лучший прогноз отмечен отдельно. Кнопка внизу ведёт к новому прогнозу.' },
  { target: '[data-profile-guide="records"]', title: 'Рекорды на трассах', text: 'Здесь личное лучшее время и число заездов на каждой трассе. «На трассу» открывает Emerald Loop.' },
  { target: '.profile-favorites', title: 'Любимые пилоты и команды', text: 'Избранное собрано в профиле. Открой карточку пилота или команды либо нажми «Изменить избранное», чтобы обновить список.' },
  { target: '[data-profile-guide="club"]', title: 'Клуб TurboTears', text: 'Участники Boosty могут открыть клубный зачёт прогнозов. Поддержка — отдельная возможность; прогнозы, игры и основные трофеи доступны всем.' },
  { target: '.profile-sharing', title: 'Покажи свой профиль', text: '«Поделиться профилем» создаёт карточку для друзей. Публичный профиль показывает полученные трофеи; ответы на прогнозы доступны после начисления баллов.' },
  { target: '.personal-hub-header, .profile-top', title: 'Аккаунт и настройки', text: 'В аккаунте — вход, привязка Telegram и проверка Boosty. В настройках — часовой пояс и напоминания. Повторить это знакомство можно кнопкой «Возможности профиля».' },
] as const;

export function readProfileGuide(userId: number): ProfileGuideStatus | null {
  try {
    const status=localStorage.getItem(key(userId));
    if(status==='completed'||status==='skipped')return status;
  } catch { /* Private and embedded browsers may deny storage. */ }
  return session.get(userId) || null;
}

export function saveProfileGuide(userId: number, status: ProfileGuideStatus) {
  session.set(userId,status);
  try { localStorage.setItem(key(userId),status); } catch { /* Keep the choice for this session. */ }
}
