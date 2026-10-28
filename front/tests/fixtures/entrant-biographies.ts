// Short Russian adaptations of the linked Wikipedia articles; historical facts through 2024.
// Only the preview uses these snapshots. Production loads the participant's own article.
const biographies: Record<string, { source: string; paragraphs: string[]; born?: string }> = {
  NOR: {
    source: 'https://en.wikipedia.org/wiki/Lando_Norris', born: '1999-11-13',
    paragraphs: [
      'Ландо Норрис — британский автогонщик, родившийся в Бристоле 13 ноября 1999 года. Он начал выступать в картинге в восемь лет, а в 2014 году выиграл чемпионат мира в старшей категории.',
      'В младших формулах Норрис стал чемпионом MSA Formula в 2015 году. В следующем сезоне он выиграл Toyota Racing Series и два первенства Формулы-Рено, а в 2017 году завоевал титул в европейской Формуле-3.',
      'После второго места в Формуле-2 в 2018 году Норрис перешёл в Формулу-1. Его дебют за McLaren состоялся на Гран-при Австралии 2019 года; напарником стал Карлос Сайнс.',
      'Первый подиум Норрис завоевал в Австрии в 2020 году, первый поул — в России в 2021-м. В Майами в 2024 году он одержал первую победу в Гран-при и завершил тот сезон вторым в чемпионате пилотов.',
    ],
  },
  PIA: {
    source: 'https://en.wikipedia.org/wiki/Oscar_Piastri', born: '2001-04-06',
    paragraphs: [
      'Оскар Пиастри — австралийский автогонщик, родившийся в Мельбурне 6 апреля 2001 года. Его путь в автоспорт начался с гонок радиоуправляемых моделей, после которых он перешёл в картинг.',
      'В 2019 году Пиастри выиграл Еврокубок Формулы-Рено с R-ace GP. Затем он стал чемпионом Формулы-3 в 2020 году и Формулы-2 в 2021-м, выступая за Prema. Три титула подряд открыли ему путь в Формулу-1.',
      'После работы в программе Alpine Пиастри присоединился к McLaren. Он дебютировал в Формуле-1 на Гран-при Бахрейна 2023 года и в том же сезоне поднялся на первый подиум в Японии.',
      'Первую победу в Гран-при австралиец одержал в Венгрии в 2024 году. Позже в том же сезоне он выиграл гонку в Азербайджане.',
    ],
  },
  mclaren: {
    source: 'https://en.wikipedia.org/wiki/McLaren',
    paragraphs: [
      'McLaren — британская гоночная команда, основанная Брюсом Маклареном в 1963 году. Её дебют в чемпионате мира Формулы-1 состоялся на Гран-при Монако в 1966 году, а первую победу основатель команды одержал в Бельгии в 1968-м.',
      'Первый Кубок конструкторов McLaren выиграла в 1974 году. В том же сезоне Эмерсон Фиттипальди стал чемпионом мира; в 1976 году титул пилотов команде принёс Джеймс Хант.',
      'В 1980-х началась одна из самых успешных эпох McLaren. За команду выступали Ники Лауда, Ален Прост и Айртон Сенна. В 1988 году Прост и Сенна вместе выиграли 15 из 16 гонок. Позже чемпионами с McLaren стали Мика Хаккинен и Льюис Хэмилтон.',
      'История McLaren выходит за пределы Формулы-1: команда выступала в Can-Am и американских гонках, а McLaren F1 GTR выиграл «24 часа Ле-Мана» в 1995 году. В Формуле-1 команда вернулась к победе в Кубке конструкторов в 2024 году.',
    ],
  },
};
const driverNationalities: Record<string, string> = { NOR: 'British', PIA: 'Australian', VER: 'Dutch', RUS: 'British', LEC: 'Monegasque', HAM: 'British', ANT: 'Italian', HAD: 'French', GAS: 'French', COL: 'Argentinian', ALB: 'Thai', SAI: 'Spanish', ALO: 'Spanish', STR: 'Canadian', LAW: 'New Zealander', LIN: 'British', OCO: 'French', BEA: 'British', HUL: 'German', BOR: 'Brazilian', PER: 'Mexican', BOT: 'Finnish' };
const teamNationalities: Record<string, string> = { mclaren: 'British', mercedes: 'German', ferrari: 'Italian', red_bull: 'Austrian', williams: 'British', aston_martin: 'British', alpine: 'French', haas: 'American', rb: 'Italian', audi: 'German', cadillac: 'American' };
export function entrantBiographyPreview(kind: 'driver' | 'team', id: string, scenario: string | null) {
  const team = kind === 'team';
  const biography = biographies[id];
  const image = team && id === 'mclaren' ? {
    url: 'https://thumb.wikimedia.org/wikipedia/commons/thumb/4/4e/McLaren_MCL38.jpg/1280px-McLaren_MCL38.jpg',
    source_url: 'https://commons.wikimedia.org/wiki/File:McLaren_MCL38.jpg',
    caption: 'McLaren MCL38 в пит-лейне Гран-при Китая, 2024 год.',
    author: 'Liauzh', license: 'CC BY-SA 4.0', license_url: 'https://creativecommons.org/licenses/by-sa/4.0/', width: 1280, height: 720,
  } : !team && id === 'NOR' ? {
    url: 'https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b0/2024_British_GP_qualifying_-_Norris.jpg/1280px-2024_British_GP_qualifying_-_Norris.jpg',
    source_url: 'https://commons.wikimedia.org/wiki/File:2024_British_GP_qualifying_-_Norris.jpg',
    caption: 'Ландо Норрис на квалификации Гран-при Великобритании, 2024 год.',
    author: '5225C', license: 'CC BY-SA 4.0', license_url: 'https://creativecommons.org/licenses/by-sa/4.0/', width: 1280, height: 960,
  } : null;
  return {
    bio: scenario === 'entrant-empty' ? '' : biography?.paragraphs.join('\n\n') || '',
    url: biography?.source || '',
    biography_source_url: biography?.source || '',
    dateOfBirth: biography?.born || '',
    nationality: scenario === 'entrant-unknown-country' ? '' : (team ? teamNationalities[id] : driverNationalities[id]) || '',
    biography_image: scenario === 'entrant-empty' || scenario === 'entrant-story-no-image' ? null : scenario === 'entrant-story-image-error' && image ? { ...image, url: '/missing-biography-image.jpg' } : image,
  };
}
