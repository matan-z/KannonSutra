import { createRouter } from './router.js';
import { bus } from './core/events.js';
import { store } from './core/store.js';
import * as visual from './visual/index.js';
import { homeScreen } from './ui/screens/home.js';
import { stageScreen } from './ui/screens/stage.js';
import { playScreen } from './ui/screens/play.js';
import { settingsScreen } from './ui/screens/settings.js';

function applySettings({ settings }) {
  const d = document.documentElement.dataset;
  d.ruby = settings.ruby ? 'on' : 'off';
  d.meaning = settings.meaning ? 'on' : 'off';
  d.vertical = settings.vertical ? 'on' : 'off';
  d.size = settings.fontSize;
}
applySettings(store.get());
store.subscribe(applySettings);

visual.init(bus, document.getElementById('fx-layer'));

createRouter(document.getElementById('app'), [
  ['/', homeScreen],
  ['/stage/:id', stageScreen],
  ['/play/:mode/:id', playScreen],
  ['/settings', settingsScreen],
]);
