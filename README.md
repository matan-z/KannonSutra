# 観音経 暗記道場（世尊偈）

観音経の世尊偈104句と、その後の結び15句（全119句）を、ゲームで暗記してひとりで読経できるようになるための HTML アプリ。
Vanilla HTML/CSS/JS（ES Modules）、ビルド不要。

## 起動
```sh
python3 -m http.server 8000
# → http://localhost:8000
```
ES Modules を使うため、`index.html` を直接開く（file://）のではなくサーバ経由で開く。

## 構成
| 場所 | 役割 |
|---|---|
| `js/data/sekai-ge.js` | 経文データ（句 ID・漢字・1字ずつの読み・段・将来の音声区間） |
| `js/core/` | `store`（localStorage 保存）、`srs`（句ごとの記憶度 0〜5）、`progress`（段の成就・功徳・コンボ）、`events`（イベントバス） |
| `js/modes/` | ① 経本 ② 穴埋め ③ 次の句は？ ④ 並べ替え ⑤ 意味あわせ ⑥ ひとり読経。`meta` と `mount(root, ctx)` を持つ |
| `js/ui/` | 部品（ルビ付き句表示など）と画面（ホーム・段・プレイ・設定） |
| `js/audio/audioService.js` | 生成音声の読み込み・区間再生・停止・エラー処理 |
| `scripts/generate_audio.py` | VOICEVOXで2種類のWAV・再生区間データを生成 |
| `js/visual/` | 演出。`index.js` が使う描画エンジンを切り替える |

ルール: 段のすべての句が記憶度3以上になると「成就」となり、次の段が開く（設定で全段を解放できる）。
第一〜十三段は各8句、結びの第十四段は15句。
意味（現代語訳）の記憶度は読みとは別に記録する（`srs` のキーは `m1`〜`m119`）。段の成就は読みだけで判定する。

## Pythonで無料の音声を作る

Python 3.9以降の標準ライブラリだけを使うため、`pip install` は不要です。
音声合成には別途、無料の [VOICEVOX](https://voicevox.hiroshiba.jp/) のインストール・起動が必要です。
APIキーや有料APIは使いません。初回にソフトと音声モデルを入手した後、生成はローカルAPIに送信します。

1. VOICEVOXを起動し、エンジンの準備が終わるまで待ちます。
2. このフォルダーで使用できる声・スタイルのIDを確認します。

```sh
python3 scripts/generate_audio.py --list-speakers
```

3. 使用する声の利用条件を確認し、一覧にあるスタイルIDを指定します。
   下の `1` は例です。まず8句だけ試作し、使用する経本と読み・長音・間を照合してください。

```sh
python3 scripts/generate_audio.py --speaker 1 --limit 8
```

4. ブラウザーを再読み込みし、第一段の「経本」で「読み方」を切り替えて試聴します。
   読みを直す場合は `js/data/sekai-ge.js` の読みを修正し、再生成します。
5. 確認後、同じ声で結びまで全119句を生成します。句数は経文データから読み取ります。

```sh
python3 scripts/generate_audio.py --speaker 1
```

MP3で生成する場合は、`ffmpeg` をインストールした環境で次を使います。
句ごとと通しのMP3を作り、アプリの再生先もMP3に切り替えます。編集用のWAVも残します。

```sh
python3 scripts/generate_audio.py --speaker 53 --format mp3
```

`53` は「麒ヶ島宗麟／ノーマル」です。別の声にする場合は一覧のIDに置き換えます。

「ゆっくり覚える」は話速0.7、「通し読み」は話速1.0で、どちらも句間0秒です。
両方とも各句の前後の無音を除去します。弱い子音を保護するため前後5msを残し、句内の発音や間は維持します。
初期値は試作用の設定です。例えば、さらにゆっくり読み、句間を2秒にするには以下を使います。

```sh
python3 scripts/generate_audio.py --speaker 1 --slow-speed 0.6 --slow-gap 2
```

出力は `assets/audio/generated/<生成条件のハッシュ>/slow/` と `continuous/` 内の
`001.wav`〜`119.wav`、各フォルダーの `full.wav`、そして `assets/audio/manifest.json` です。
同じ条件で再実行すると、検証できた句のWAVを再利用して途中から再開できます。
両方が完成してからマニフェストを更新するため、失敗した生成で既存の完成音声を置き換えません。
過去の生成ファイルは残るので、不要になった世代は確認して手動で削除できます。

アプリはマニフェストを読み込み、選んだ段の範囲を通しWAVから再生します。
`SUTRA_TITLE` の経題も両方の音声の先頭に収録します。第一段と通し読経は経題から始まり、
本文の字をタップした場合はその句から始まります。経題は本文119句の番号・記憶度には含めません。
8句の試作時は第一段だけ音声を選べます。全119句の生成後はホームの「通しで読む」でも聞けます。
音声がない範囲でも、音声なしの文字ガイドを利用できます。
句内の文字の強調は時間を均等分割した目安で、正確な文字単位の発音同期ではありません。
通しWAVは句ごとの合成音声を結合したものなので、つなぎ目は試聴して確認してください。

読み原稿だけならVOICEVOXを起動せずに出力できます。

```sh
python3 scripts/generate_audio.py --export-text /tmp/sekaige-yomi.txt
```

VOICEVOXのポートが異なる場合は `--engine http://127.0.0.1:ポート番号` を指定してください。
起動中のエンジンのAPI仕様は `http://127.0.0.1:50021/docs` でも確認できます。
[公式エンジンのAPI例](https://github.com/VOICEVOX/voicevox_engine#http-リクエストで音声合成するサンプルコード)

### 音声の位置づけとクレジット

作られるのは合成音声による読み上げで、宗派固有の節回しを備えた読経のお手本ではありません。
節回しの教材には別途、適切な読経録音を用意してください。
アプリの音声選択時には合成音声であることと `VOICEVOX:話者名` を表示します。
[VOICEVOXの利用規約](https://voicevox.hiroshiba.jp/term/) と、選んだ声の個別の条件も確認してください。

### 参考音声に合わせた音程調整

`scripts/adjust_audio_pitch.py` は生成済みのWAVを使い、参考音声の基本周波数を解析して音程を調整します。
参考音声の基準音と緩やかな音程変化を参考に、合成音声の音程を調整します。
結びの長行は同じ基準音で調整します。以前と同じ参考音程で、読みが一致する既存の調整済み音声はそのまま再利用します。
経題も同じ基準音で調整します。追加・変更された経題だけを生成し、本文の音声を再利用して冒頭に結合できます。
これは声や発声・節回し全体の再現ではなく、基本周波数の傾向を参考にした調整です。
参考音声の波形は出力に混ぜません。

```sh
python3 -m venv /tmp/kannongyo-pitch-venv
/tmp/kannongyo-pitch-venv/bin/python -m pip install -r scripts/requirements-audio-pitch.txt
/tmp/kannongyo-pitch-venv/bin/python scripts/adjust_audio_pitch.py --reference /tmp/kannongyo-reference.wav
```

`--reference` には解析に使うローカルWAVを指定します。音程調整後、両方の音声の各句の前後の無音を除去し、句間0秒で結合します。
経文を追加・修正した場合は、VOICEVOXを起動して同じコマンドを実行します。
足りない句・読みが変更された句だけを以前と同じ話者で生成し、音程を調整して全体を結合します。
`generate_audio.py` を先に実行する必要はありません。元の偈と結びはともに経文データから読み取ります。
全句の処理と音程の検証後、アプリの音声を切り替えます。処理中にマニフェストが変更されていた場合は切り替えません。
以前の音声は元の生成フォルダーに残り、以前のマニフェストも `assets/audio/manifest-before-pitch-*.json` に保存します。
修正版の通しMP3は `assets/audio/kannongyo-sekaige-slow-tuned.mp3` と
`assets/audio/kannongyo-sekaige-continuous-tuned.mp3` です。
結びまで含む完成版は `assets/audio/kannongyo-complete-slow.mp3` と
`assets/audio/kannongyo-complete-continuous.mp3` にも保存します。
経題だけのMP3は `assets/audio/kannongyo-title-slow.mp3` と `assets/audio/kannongyo-title-continuous.mp3` です。
マニフェストでは経題の音声・区間を各プロファイルの `title` に保存し、本文の区間を経題の長さだけ後ろへ移します。

既存の音程・話速を維持したまま句間だけ直す場合は、次のコマンドを使います。VOICEVOXや参考音声は不要で、Python標準ライブラリとffmpegだけで実行できます。

```sh
python3 scripts/tighten_continuous_audio.py
python3 scripts/tighten_continuous_audio.py --profile slow
```

各句のWAVを無音除去してから結合・MP3化し、アプリの句ごとの再生位置も更新します。
指定した種類の音声だけを更新し、以前のマニフェストは `assets/audio/manifest-before-timing-*.json` に保存します。

### 雑音の低減と残響

`scripts/polish_audio.py` は低いポップ音・クリック・句のつなぎ目を補正し、声に残響を加えます。
合成時に前回の参考音声の基準音を直接指定して全体を生成する場合は、VOICEVOXを起動して次を実行します。
この方法では録音後のWORLDによる音程変更を行いません。無声の子音は無声のまま残します。

```sh
/tmp/kannongyo-pitch-venv/bin/python scripts/polish_audio.py --native-pitch
```

`--native-pitch` を省略すると、既存音声の雑音低減・残響処理だけを行います。
元の音声は残し、各句の `sourceWav` に保存先を記録します。再処理してもエコーが重複しません。
句間の無音は加えず、句ごとの再生位置をサンプル数から更新します。
最後に約0.85秒の残響を残し、アプリの通し再生ではこの余韻まで再生します。
残響の長さや強さはスクリプト冒頭の `SETTINGS` で変更できます。
音声を別のスクリプトで作り直した後は、必要に応じてこの処理を再実行してください。
以前の設定は `assets/audio/manifest-before-polish-*.json` に保存します。

音程調整・雑音低減・残響の検証は、追加ライブラリを入れたPython環境で実行します。

```sh
/tmp/kannongyo-pitch-venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

### 読経の発音・拍・抑揚

`scripts/chant_audio.py` は歌唱用のフレーム合成を使い、読経の長音・拍・音程変化を指定します。
漢字ごとの読みを保ち、「とう」「みょう」「そう」などは別の母音を発音し直すのではなく、
母音を伸ばして発音します。「がい」などの別の母音への移行や、撥音・促音は残します。
参考動画から測定した約0.67秒の拍を1字に割り当て、ゆっくり版はその0.7倍のテンポにします。
一音だけの固定音程にはせず、参考から抽出した音程曲線の小さな上下を反映します。

```sh
# 冒頭と指摘のあった句を2つの声で試聴用に生成
/tmp/kannongyo-pitch-venv/bin/python scripts/chant_audio.py
# これまでと同じ声（麒ヶ島宗麟）で経題・全119句を生成し、雑音低減・残響処理後に公開
/tmp/kannongyo-pitch-venv/bin/python scripts/chant_audio.py --publish --singers 3053
# 青山龍星に変更する場合は --singers 3013
```

VOICEVOXの起動が必要です。歌唱の音素・長さ推定には6000、声の生成には3053または3013を使います。
使い方は [VOICEVOX公式の歌声合成APIの例](https://github.com/VOICEVOX/voicevox_engine#http-リクエストで歌声合成するサンプルコード) を参照しています。
参考の音程・時刻だけを `scripts/data/kannongyo-reference-pitch.npz` に保存しており、動画の音声波形は出力に混ぜません。
拍による対応付けは近似で、動画の発音位置を手作業で逐一照合したものではありません。
自然さの評価は試聴を必要とします。音程の数値が一致するだけで自然と判断しないでください。
経題・本文の句番号は変えず、実際の音素の開始位置から再生位置を更新します。

### 別エンジンでの短い試聴

`scripts/preview_qwen_audio.py` は
[Qwen3-TTS VoiceDesign](https://github.com/QwenLM/Qwen3-TTS) の内部診断用です。
独自のint8量子化を使った試聴版は、日本語として成立しないとの評価で不採用です。
失敗したファイルは `assets/audio/previews/rejected/qwen/` に退避しました。
量子化を除いたfloat32構成で、まず日常の日本語を確認するための `--case ordinary` を用意しています。
音声が終了トークンに到達せず長さ上限で途切れた場合は、出力せずエラーにします。
出力先の初期値は `/tmp/kannongyo-qwen-diagnostics/` で、アプリの音声は更新しません。
音声認識の一致だけで読経の発音・節回しの自然さを保証することはできません。

```sh
python3 -m venv /tmp/kannongyo-qwen-venv
/tmp/kannongyo-qwen-venv/bin/pip install torch==2.14.1 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cpu
/tmp/kannongyo-qwen-venv/bin/pip install -r scripts/requirements-audio-qwen.txt
/tmp/kannongyo-qwen-venv/bin/python scripts/preview_qwen_audio.py --case ordinary --max-new-tokens 128
```

初回は公式モデル約4.5GBを取得します。float32のCPU実行には約10GBを目安としたメモリーと時間が必要です。
ローカルモデルがある場合は `--model /tmp/kannongyo-qwen-model` のように指定できます。

### 検証

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
node --experimental-default-type=module --test tests/audio-service.test.mjs
```

テストはAPI応答を代用し、WAVの結合時刻・再実行・失敗時の保持・再生制御を確認します。
実際の発音・声質・VOICEVOXとの接続は、実エンジンでの生成と試聴で確認してください。

## 3D（Blender / Three.js）を入れるとき
- ゲームロジックは `bus.emit('answer' | 'stage:clear', …)` を出すだけで描画を知らない
- `js/visual/renderer3d.js` に `init(bus, layer)` / `mountHome(el, { ratio, beads })` / `lotusSVG()` 相当を実装し、
  `js/visual/index.js` の export 先を差し替える。`.glb` は `assets/models/` へ
- 2D 版はフォールバックとして残す

## 経文データについて
漢字・読みは手入力。お手元の経本と1句ずつ照合すること。宗派で読みが違う句は、データに `yomiAlt` を足して対応する想定。

## ライセンス
コードは [MIT License](LICENSE) です。ただし、`assets/audio/` の音声はMITの対象外で、[VOICEVOXの利用規約](https://voicevox.hiroshiba.jp/term/)と音声ライブラリ（VOICEVOX:麒ヶ島宗麟）の利用条件に従います。
