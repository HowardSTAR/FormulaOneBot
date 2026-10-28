// Authoring fixture: render the game's scenery once, without gameplay or API calls.
import * as Phaser from '../../race-game/node_modules/phaser/dist/phaser.esm.js';
import { drawTrack } from '../../race-game/src/trackRenderer';
import { tracks } from '../../race-game/src/tracks';
const track = tracks.find(track => track.id === new URLSearchParams(location.search).get('track'));
if (!track) throw new Error('Unknown track');
class Preview extends Phaser.Scene {
  preload() { if (track!.image) this.load.image('track', `/race-game/assets/${track!.image}`); }
  create() {
    drawTrack(this, track!);
    this.game.events.once(Phaser.Core.Events.POST_RENDER, () => { document.documentElement.dataset.ready = 'true'; });
  }
}
new Phaser.Game({ type: Phaser.CANVAS, width:1536, height:1024, backgroundColor:'#141518', scene:Preview, audio:{noAudio:true}, banner:false });
