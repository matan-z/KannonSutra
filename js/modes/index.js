// モード一覧（段の画面に表示する順番）
import * as learn from './learn.js';
import * as fill from './fillBlank.js';
import * as next from './nextPhrase.js';
import * as order from './reorder.js';
import * as meaning from './meaning.js';
import * as chant from './chant.js';

export const MODES = [learn, fill, next, order, meaning, chant];
export const getMode = (key) => MODES.find((m) => m.meta.key === key) ?? null;
