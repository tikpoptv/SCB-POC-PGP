# Java PGP Runner

งานของน้อง: implement PGP encrypt/decrypt **2 variant** (in-memory + streaming)
อ่านโจทย์เต็มที่ `docs/handoff-java-inmem-variant.md` (อันนั้นเป็นหลัก)

## สิ่งที่ให้มาแล้ว
- `pom.xml` — Maven + Bouncy Castle + Jackson + JUnit (fat-jar)
- กุญแจ: `keys/rsa2048-*.asc`, `keys/rsa4096-*.asc` (ไม่มี passphrase) — ดู `keys/KEYINFO.md`
- ไฟล์ทดสอบ: `corpus/sample.txt`, `corpus/sample.csv`, `corpus/sample.pdf`

## โครงที่ให้ (เหลือไว้ให้เขียนเอง)
```
src/main/java/com/poc/pgp/
  JavaRunner.java   # main: stub — เขียน CLI/loop/timing เอง
  PgpEngine.java    # interface — สร้าง InMemoryEngine + StreamingEngine เอง
src/test/java/com/poc/pgp/
  EngineTest.java   # stub — เขียนเทสต์เอง
```

## Build & Run
```
cd runners/java
mvn clean package
echo '{"command":"run","variantId":"java-inmem-single","keySetPath":"../../keys","corpusPath":"../../corpus","outputDir":"./out"}' \
  | java -jar target/java-inmem-runner-0.1.0.jar
```

## ต้องทำ
1. `JavaRunner.main` — อ่าน JSON stdin, วนไฟล์, จับเวลา, พิมพ์ JSON stdout (log ออก stderr)
2. `InMemoryEngine` + `StreamingEngine` (implement `PgpEngine`) — AES-256/ZLIB/SHA-256/RSA, binary
3. ข้าม `.ctrl`/`.ctl`, รองรับไฟล์ว่าง
4. เขียนเทสต์ใน `EngineTest` ให้ครอบคลุม round-trip ทั้ง 2 variant + ไฟล์ว่าง

Definition of Done อยู่ใน `docs/handoff-java-inmem-variant.md`
