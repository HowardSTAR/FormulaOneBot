export type DetailedCircuit = {
  name: string; season: number; viewBox: string; source: string; revision: string;
  sectors: string[]; pitLane: string; corners: [number, number, number][];
  zones: { name: string; path: string; description: string }[];
  detection: [number, number]; activation: [number, number]; finish: [number, number];
  finishAngle: number; direction: string;
  detectionDescription: string; activationDescription: string; sectorDescription: string;
};

// Schematic coordinates, manually reviewed against FIA Competition Notes, page 2.
// Do not reuse across seasons: operational zones and circuit configurations change.
const hungary2026: DetailedCircuit = {
  name: 'Хунгароринг', season: 2026, viewBox: '40 270 1000 1110',
  source: 'https://www.fia.com/system/files/decision-document/2026_hungarian_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_red_zone.pdf',
  revision: 'FIA · карта V2 · 21.07.2026',
  sectors: [
    'M450 1230 L103 900 Q60 855 113 858 Q210 852 266 903 L382 1001 Q421 1037 450 999 Q470 978 449 931 L414 885 Q405 867 419 838 L550 600',
    'M550 600 L590 548 Q604 534 599 516 L568 397 Q556 351 596 338 Q633 324 670 353 Q709 375 771 472 Q793 486 774 502 Q762 510 766 528 L791 628 Q796 651 823 654 L877 664 Q914 673 909 712 L892 815 Q886 846 902 873 L942 939 Q969 978 938 1011 L887 1060',
    'M887 1060 L749 1208 Q732 1228 716 1209 L659 1144 L610 1108 Q580 1088 564 1115 Q550 1143 579 1166 L652 1227 Q681 1257 665 1288 Q647 1323 606 1312 Q597 1310 580 1295 L450 1230',
  ],
  pitLane: 'M653 1228 Q675 1263 650 1287 Q633 1302 607 1291 L165 921 Q130 899 115 860',
  corners: [[1,102,818],[2,468,1050],[3,458,870],[4,638,546],[5,601,302],[6,815,475],[7,728,535],[8,830,618],[9,950,689],[10,850,830],[11,992,981],[12,731,1172],[13,538,1097],[14,700,1324]],
  zones: [
    {name:'SM A1',path:'M552 1302 L127 944',description:'Активация: 40 м после T14; при низком сцеплении — 100 м после T14.'},
    {name:'SM A2',path:'M185 838 Q232 851 278 887 L377 969',description:'Активация: 30 м после входа в T1A; при низком сцеплении — 100 м после входа в T1A.'},
    {name:'SM A3',path:'M461 811 L558 636',description:'Активация: 50 м после T3; при низком сцеплении — 80 м после T3.'},
    {name:'SM A4',path:'M943 1038 L810 1180',description:'Активация: 60 м после T11; при низком сцеплении — 90 м после T11.'},
  ],
  detection:[652,1227], activation:[620,1314], finish:[450,1230],
  finishAngle: -48, direction: 'M346 1140 l-15 -26 29 10',
  detectionDescription: 'Вход в T14', activationDescription: '30 м до выхода из T14',
  sectorDescription: 'S1 → S2: 85 м до T4. S2 → S3: 100 м после T11.',
};

const austria2026: DetailedCircuit = {
  name: 'Ред Булл Ринг', season: 2026, viewBox: '45 425 935 645',
  source: 'https://www.fia.com/system/files/decision-document/2026_austrian_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_red_zone.pdf',
  revision: 'FIA · карта V3 · 22.06.2026',
  sectors: [
    'M705 916 L445 985 Q434 990 427 977 L325 822 Q293 774 261 695 Q235 632 212 613 L183 584',
    'M183 584 L114 514 Q101 500 120 498 Q175 486 229 494 L442 529 Q497 538 584 539 Q623 537 603 571 Q568 628 520 633 Q478 641 383 619 Q346 607 331 643 Q318 668 333 696 L358 741',
    'M358 741 L377 775 Q407 809 445 783 Q471 741 510 725 Q530 717 570 717 L820 715 Q856 714 866 752 L893 832 Q904 853 866 872 L705 916',
  ],
  pitLane: 'M869 764 Q878 833 854 852 Q825 877 744 890 L650 912 L510 956 L462 979',
  corners: [[1,414,1022],[2,254,622],[3,93,481],[4,641,544],[5,575,645],[6,368,666],[7,417,750],[8,510,694],[9,871,695],[10,933,849]],
  zones: [
    {name:'SM A1',path:'M828 894 L477 992',description:'Активация: 110 м после T10; при низком сцеплении — 160 м после T10.'},
    {name:'SM A2',path:'M382 927 L316 827 Q286 782 251 702 Q221 631 200 614 L128 541',description:'Активация: 110 м после T1; при низком сцеплении — 170 м после T1.'},
    {name:'SM A3',path:'M178 479 L230 481 L443 516 Q497 525 547 525',description:'Активация: 90 м после T3; при низком сцеплении — 160 м после T3.'},
    {name:'SM A4',path:'M556 701 L806 701',description:'Активация: 10 м после T8; при низком сцеплении — 60 м после T8.'},
  ],
  detection:[888,819], activation:[832,882], finish:[705,916],
  finishAngle: -15, direction: 'M617 933 l-22 17 27 5',
  detectionDescription: '50 м до T10', activationDescription: '110 м после T10',
  sectorDescription: 'S1 → S2: 170 м до T3. S2 → S3: 60 м до T7. Длина секторов: 1,215 / 1,697 / 1,414 км.',
};

const italy2026: DetailedCircuit = {
  name: 'Монца', season: 2026, viewBox: '185 255 670 1010',
  source: 'https://www.fia.com/system/files/decision-document/2026_italian_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_red_zone.pdf',
  revision: 'FIA · карта V2 · 03.09.2026',
  sectors: [
    'M255 999 L289 619 Q287 609 298 612 L308 612 Q314 612 310 599 Q295 564 299 529 L302 482 Q312 393 390 373 Q425 360 504 358',
    'M504 358 L591 353 Q602 354 601 342 Q601 333 611 333 Q656 326 725 298 Q764 283 769 329 L778 423 Q780 433 767 440 L646 510 Q617 530 592 553 L480 650',
    'M480 650 L427 697 Q420 702 422 719 L423 731 Q423 744 411 752 L400 761 Q392 766 391 782 L351 1160 Q349 1194 320 1198 Q284 1203 267 1159 Q250 1126 255 1080 L255 999',
  ],
  pitLane: 'M283 1183 Q252 1146 254 1102 L268 999 L279 924 L273 843 L277 773',
  corners: [[1,253,589],[2,340,622],[3,322,360],[4,580,393],[5,607,302],[6,800,299],[7,808,449],[8,458,706],[9,456,758],[10,355,782],[11,313,1233]],
  zones: [
    {name:'SM A1',path:'M240 1118 L241 1068 L273 647',description:'Активация: 30 м после T11 / выхода из пит-лейна; при низком сцеплении — 100 м после T11 / выхода из пит-лейна.'},
    {name:'SM A2',path:'M418 346 L576 341',description:'Активация: 70 м после T3; при низком сцеплении — 110 м после T3.'},
    {name:'SM A3',path:'M695 466 L638 498 Q610 519 582 542 L438 677',description:'Активация: 170 м после T7; при низком сцеплении — 230 м после T7.'},
    {name:'SM A4',path:'M400 826 L372 1099',description:'Активация: 130 м после T10; при низком сцеплении — 180 м после T10.'},
  ],
  detection:[350,1169], activation:[291,1186], finish:[255,999],
  finishAngle: 5, direction: 'M259 970 l-10 -22 -12 22',
  detectionDescription: 'Вход в T11', activationDescription: 'T11',
  sectorDescription: 'S1 → S2: 230 м до T4. S2 → S3: 210 м до T8. Длина секторов: 1,909 / 1,823 / 2,061 км.',
};

const australia2026: DetailedCircuit = {
  name: 'Альберт-Парк', season: 2026, viewBox: '80 275 885 990',
  source: 'https://www.fia.com/system/files/decision-document/2026_australian_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_quarantine_zone.pdf',
  revision: 'FIA · карта V2 · 03.03.2026',
  sectors: [
    'M456 985 L330 862 Q321 855 328 845 Q347 811 325 780 L239 694 Q185 630 153 573 Q146 560 161 557 L205 549 Q226 545 220 523 L217 442 Q217 431 228 422 Q282 377 333 362',
    'M333 362 Q368 348 385 335 Q399 327 412 340 Q433 358 458 356 Q522 358 547 410 Q560 435 566 488 Q574 524 556 571 Q530 630 523 666 Q509 755 571 814 L587 828',
    'M587 828 L638 872 Q645 879 660 877 L701 872 Q708 869 714 877 L793 940 Q823 964 833 1000 L871 1132 L878 1150 Q883 1160 870 1162 L779 1187 Q749 1198 734 1174 L692 1101 Q682 1086 675 1099 L650 1125 Q627 1149 600 1121 L456 985',
  ],
  pitLane: 'M652 1126 Q625 1158 591 1126 L437 981 Q402 948 386 916 L349 882',
  corners: [[1,306,875],[2,372,815],[3,119,559],[4,251,529],[5,251,441],[6,399,306],[7,442,387],[8,571,383],[9,644,906],[10,727,842],[11,922,1158],[12,751,1230],[13,699,1064],[14,614,1170]],
  zones: [
    {name:'SM A1',path:'M584 1121 L348 895',description:'Активация: 50 м после T14; при низком сцеплении — 100 м после T14.'},
    {name:'SM A2',path:'M295 769 L229 704 Q180 647 151 596',description:'Активация: 20 м после T2; при низком сцеплении — 45 м после T2.'},
    {name:'SM A3',path:'M255 394 Q299 365 372 338',description:'Активация: 85 м после T5; при низком сцеплении — 125 м после T5.'},
    {name:'SM A4',path:'M573 446 Q591 512 568 575 Q539 640 536 674 Q522 754 580 803',description:'Активация: 35 м после T8. В этой версии карты точка для низкого сцепления не предусмотрена.'},
    {name:'SM A5',path:'M744 891 L802 933 Q835 960 847 1004 L876 1103',description:'Активация: 60 м после T10. В этой версии карты точка для низкого сцепления не предусмотрена.'},
  ],
  detection:[672,1103], activation:[648,1128], finish:[456,985],
  finishAngle: -47, direction: 'M426 953 l-23 -9 9 23',
  detectionDescription: '15 м после T13', activationDescription: 'Вход в T14',
  sectorDescription: 'S1 → S2: 120 м до T6. S2 → S3: 140 м до T9. Длина секторов: 1,753 / 1,413 / 2,112 км.',
};

export const detailedCircuits: Record<string, DetailedCircuit> = {
  'Hungarian Grand Prix': hungary2026,
  'Austrian Grand Prix': austria2026,
  'Italian Grand Prix': italy2026,
  'Australian Grand Prix': australia2026,
};

export function getDetailedCircuit(eventName: string, season: number): DetailedCircuit | null {
  const circuit = Object.hasOwn(detailedCircuits, eventName) ? detailedCircuits[eventName] : null;
  return circuit?.season === season ? circuit : null;
}
