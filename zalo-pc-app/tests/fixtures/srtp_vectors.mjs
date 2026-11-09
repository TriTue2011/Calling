// Sinh vector SRTP chuan tu @softtynet/zca-js 2.3.13 (ZaloSrtpSession) de doi chieu ban Python.
import { createRequire } from 'node:module';
const modPath = process.argv[2];
const { ZaloSrtpSession } = await import(modPath);
const key = Buffer.from(Array.from({length: 30}, (_, i) => (i * 7 + 3) & 0xff));
function rtp(seq, ts, ssrc, payload) {
  // Header PC 20 byte: 0x90 0x70 seq ts ssrc BEDE 0001 ext(4)
  const h = Buffer.alloc(20);
  h[0] = 0x90; h[1] = 0x70; h.writeUInt16BE(seq, 2); h.writeUInt32BE(ts >>> 0, 4); h.writeUInt32BE(ssrc >>> 0, 8);
  h[12] = 0xbe; h[13] = 0xde; h.writeUInt16BE(1, 14); h[16] = 0x51;
  return Buffer.concat([h, payload]);
}
const out = { key_b64: key.toString('base64'), suites: {} };
for (const suite of ['AES_CM_128_HMAC_SHA1_80', 'AES_CM_128_HMAC_SHA1_32']) {
  const s = new ZaloSrtpSession(key, suite);
  const seqs = [65530, 65531, 65532, 65533, 65534, 65535, 0, 1, 2, 3];   // qua vong -> ROC tang
  const pk = [];
  seqs.forEach((seq, i) => {
    const payload = Buffer.from(Array.from({length: 40 + i * 13}, (_, j) => (j * 31 + i) & 0xff));
    const plain = rtp(seq, 160 * i + 1000, 0xA1B2C3D4, payload);
    pk.push({ rtp: plain.toString('hex'), srtp: s.protectRtp(plain).toString('hex') });
  });
  out.suites[suite] = pk;
}
console.log(JSON.stringify(out));
