# Requirements Document

## Introduction

เอกสารนี้กำหนดความต้องการสำหรับ Proof of Concept (POC) เพื่อ **เปรียบเทียบประสิทธิภาพการเข้ารหัส (encrypt) และถอดรหัส (decrypt) แบบ PGP ระหว่างภาษา Go และ Java (Spring Boot) เท่านั้น** เป้าหมายคือสรุปว่าภาษาใดเหมาะสมกว่าสำหรับ workload การทำ PGP encrypt/decrypt ภายใต้เงื่อนไขที่ "ยุติธรรมและทำซ้ำได้" (fair and reproducible)

ขอบเขตของ POC นี้จงใจให้แคบและชัดเจน:

- **อยู่ในขอบเขต (In scope):** การวัดเวลาและทรัพยากรของการ encrypt/decrypt แบบ PGP, การรันบนเครื่อง (VM) เดียวกัน, การใช้ชุดกุญแจและชุดไฟล์ทดสอบและค่าตั้งค่า algorithm เดียวกัน, การรันสลับลำดับ (alternating) ระหว่างสองภาษาหลายรอบ, การมีหลายรูปแบบการเขียนโค้ด (implementation variants) ต่อภาษา แล้วคัดตัวที่ดีที่สุดของแต่ละภาษามาแข่งกัน, การเก็บ metrics ครบชุด, และการสรุปผล
- **อยู่นอกขอบเขต (Out of scope):** ฐานข้อมูล, REST/HTTP API, การเรียกผ่านเครือข่าย, connection pool, message queue, บริการภายนอกอื่น ๆ ทั้งหมด และการลงลายเซ็นดิจิทัล (signing) กับการตรวจสอบลายเซ็น (signature verification) ซึ่งไม่อยู่ในการวัดของ POC นี้

เอกสารนี้ยังครอบคลุม edge cases และ scenarios ที่อาจมีผลต่อผลลัพธ์ (เช่น ขนาดไฟล์ที่ต่างกัน, ชนิด/ขนาดของกุญแจ, streaming เทียบกับ in-memory, การทำงานแบบขนาน, ผลของ GC, ผลของ JIT warm-up, และค่าตั้งค่า cipher/compression) ตามที่ผู้ใช้ต้องการให้ "ส่งมอบเกินกว่าที่ขอ" (over-deliver)

## Glossary

- **Benchmark_Harness**: ระบบควบคุมหลักที่จัดลำดับการรัน, สั่งรัน implementation ของแต่ละภาษา, เก็บผลการวัด และรวมผลลัพธ์
- **Go_Runner**: โปรแกรมที่เขียนด้วยภาษา Go ซึ่งทำ PGP encrypt/decrypt ตามรูปแบบ (variant) ที่กำหนด
- **Java_Runner**: โปรแกรมที่เขียนด้วย Java/Spring Boot ซึ่งทำ PGP encrypt/decrypt ตามรูปแบบ (variant) ที่กำหนด
- **Runner**: คำรวมที่หมายถึง Go_Runner หรือ Java_Runner ตัวใดตัวหนึ่ง
- **Implementation_Variant**: รูปแบบการเขียนโค้ด PGP หนึ่งแบบภายในภาษาหนึ่ง (เช่น in-memory, streaming, parallel) แต่ละภาษามีได้หลาย variant
- **Best_Variant**: Implementation_Variant ที่ให้ผลดีที่สุดของแต่ละภาษา ซึ่งถูกคัดเลือกตามเกณฑ์ที่กำหนด เพื่อนำไปแข่งแบบ head-to-head
- **Test_Corpus**: ชุดไฟล์ทดสอบที่ใช้ร่วมกันทุกภาษาและทุก variant ประกอบด้วยไฟล์ชนิดจริงที่รองรับ ได้แก่ .txt, .xlsx, .xls, .csv, .pdf, .zip, .7z, .dat และ .gz รวมถึงไฟล์ชนิด .ctrl และ .ctl ที่กำหนดให้ข้ามการเข้ารหัส (ดูรายละเอียดใน Requirement 32)
- **Key_Set**: ชุดกุญแจ PGP (public/private key pairs) ที่ใช้ร่วมกันทุกภาษาและทุก variant
- **Crypto_Profile**: ชุดค่าตั้งค่า algorithm ของ PGP (เช่น public-key algorithm, symmetric cipher, compression, hash) ที่ใช้ร่วมกัน
- **Benchmark_Run**: การรันทดสอบครบหนึ่งรอบสำหรับ scenario และ variant ที่กำหนด
- **Round**: หนึ่งรอบของการรันแบบสลับลำดับ ซึ่งภายในประกอบด้วยการรันทั้ง Go และ Java
- **Scenario**: ชุดเงื่อนไขการทดสอบหนึ่งชุด (เช่น ขนาดไฟล์, ชนิดกุญแจ, ระดับ concurrency, โหมด streaming/in-memory)
- **Metric_Record**: หน่วยข้อมูลผลการวัดหนึ่งรายการที่บันทึกจาก Benchmark_Run หนึ่งครั้ง
- **Result_Report**: เอกสาร/ไฟล์ผลลัพธ์สรุปที่ Benchmark_Harness สร้างขึ้นเมื่อจบการทดสอบ
- **Warm_Up_Iteration**: การรันก่อนเก็บผลจริง เพื่อให้ runtime เข้าสู่สภาวะเสถียร (เช่น JIT, cache)
- **Operator**: ผู้ใช้ที่กำหนดค่าและสั่งรัน Benchmark_Harness
- **Cold_Start**: โหมดการวัดที่รัน encrypt/decrypt ให้จบภายใน process เดียว โดยนับรวมเวลาเริ่มต้น process (process startup) และเวลา JIT warm-up เข้าในผลการวัด เพื่อสะท้อน workload แบบ process สั้น (เช่น CLI, batch, serverless)
- **Steady_State**: โหมดการวัดที่เก็บผลหลังจาก runtime ผ่านการ warm-up จนเข้าสู่สภาวะเสถียรแล้ว เพื่อสะท้อน workload แบบ service ที่รันต่อเนื่องยาวนาน
- **Native_Image_Variant**: Implementation_Variant ของ Java ที่ถูก compile เป็น native binary (เช่น ด้วย GraalVM Native Image) แทนการรันบน JVM แบบปกติ
- **Hardware_Acceleration**: การใช้คำสั่งเร่งความเร็วการเข้ารหัสระดับ CPU (เช่น AES-NI) เพื่อเพิ่มความเร็วของ symmetric cipher
- **Interoperability_Check**: การตรวจสอบว่า ciphertext ที่ Runner หนึ่งสร้างขึ้นสามารถถูกถอดรหัสได้โดย Runner อื่นและ/หรือเครื่องมือมาตรฐาน (เช่น gpg CLI) โดยให้ผลลัพธ์เป็น pass/fail
- **Noise_Floor**: ระดับความผันผวนพื้นฐานของ Benchmark_Harness และเครื่องที่วัดได้จาก null test (รัน Runner ชนิดเดียวกันแข่งกับตัวเอง เช่น Go vs Go หรือ Java vs Java) เพื่อใช้เป็นฐานเทียบว่าความต่างที่วัดได้มาจากภาษาจริงหรือจาก noise ของเครื่อง
- **Soak_Test**: Scenario ที่รันต่อเนื่องเป็นเวลานานหรือมีจำนวน operation มาก เพื่อตรวจหา memory leak, การถดถอยของประสิทธิภาพตามเวลา (performance degradation) และพฤติกรรม garbage collection ระยะยาว
- **Process_Startup_Time**: ระยะเวลาตั้งแต่เริ่มต้น process ของ Runner จนถึงจุดที่ Runner พร้อมเริ่มทำงาน encrypt/decrypt ครั้งแรก
- **Coefficient_Of_Variation**: ค่าสัมประสิทธิ์การกระจาย (CV) คำนวณจากค่าเบี่ยงเบนมาตรฐานหารด้วยค่าเฉลี่ย ใช้ประเมินความเสถียรของชุดผลการวัด

## Requirements

### Requirement 1: ขอบเขตของ POC จำกัดเฉพาะ PGP encrypt/decrypt

**User Story:** ในฐานะ Operator ฉันต้องการให้ POC โฟกัสเฉพาะการเข้ารหัส/ถอดรหัส PGP เท่านั้น เพื่อให้ผลการเปรียบเทียบสะท้อนสมรรถนะของภาษาในงานนี้ล้วน ๆ โดยไม่มีปัจจัยอื่นมารบกวน

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL วัด core crypto-time metric (เมตริกที่ใช้ในการเปรียบเทียบแบบ steady-state, throughput และ latency) เป็นระยะเวลาที่ใช้ไปกับการเรียก PGP encrypt และ PGP decrypt เท่านั้น โดยไม่นับรวมเวลาการสร้างหรือโหลดกุญแจ เวลาการอ่าน/เขียนไฟล์ และช่วง warm-up เข้าใน core crypto-time metric และ THE Benchmark_Harness SHALL บันทึกเวลา Cold_Start (process startup และ JIT warm-up ตาม Requirement 21) เป็น metric เสริมที่มีป้ายกำกับแยกต่างหาก โดยไม่นำมารวมเข้าใน core crypto-time metric
2. THE Benchmark_Harness SHALL ทำงานโดยไม่เชื่อมต่อฐานข้อมูล, REST/HTTP API, ระบบเครือข่ายภายนอก, connection pool, หรือบริการภายนอกอื่นใด
3. WHEN Operator ตั้งค่าและสั่งรัน Benchmark_Run, THE Benchmark_Harness SHALL อ่านข้อมูลนำเข้าจากไฟล์ในเครื่องและเขียนผลลัพธ์ลงไฟล์ในเครื่องเท่านั้น
4. IF ไฟล์ข้อมูลนำเข้าไม่พบหรือไม่สามารถอ่านได้, THEN THE Benchmark_Harness SHALL ยุติการทำงานของ Benchmark_Run โดยไม่เขียนไฟล์ผลลัพธ์ที่ไม่สมบูรณ์ และแสดงข้อความแสดงข้อผิดพลาดที่ระบุสาเหตุของความล้มเหลว
5. THE Benchmark_Harness SHALL จำกัดการเปรียบเทียบไว้เพียงสองภาษาคือ Go และ Java (Spring Boot)
6. THE Benchmark_Harness SHALL จำกัดการวัดไว้ที่การ encrypt และ decrypt แบบ PGP เท่านั้น โดยไม่รวมการลงลายเซ็นดิจิทัล (signing) และการตรวจสอบลายเซ็น (signature verification) ซึ่งอยู่นอกขอบเขตของ POC นี้

### Requirement 2: ใช้เวอร์ชันล่าสุดของทั้งสองภาษา

**User Story:** ในฐานะ Operator ฉันต้องการให้ใช้เวอร์ชันล่าสุดของ Go และ Java/Spring Boot เพื่อให้ผลการเปรียบเทียบสะท้อนความสามารถปัจจุบันของแต่ละภาษา

#### Acceptance Criteria

1. WHEN เริ่มทำ POC, THE Go_Runner SHALL ถูก build และรันด้วย Go เวอร์ชัน stable ล่าสุดที่เผยแพร่อย่างเป็นทางการบนเว็บไซต์ทางการของ Go ณ วันที่เริ่มทำ POC ที่บันทึกไว้ใน Result_Report
2. WHEN เริ่มทำ POC, THE Java_Runner SHALL ถูก build และรันด้วย Java (JDK) เวอร์ชัน LTS หรือ stable ล่าสุดที่เผยแพร่อย่างเป็นทางการ และ Spring Boot เวอร์ชัน stable ล่าสุดที่เผยแพร่อย่างเป็นทางการ ณ วันที่เริ่มทำ POC ที่บันทึกไว้ใน Result_Report
3. THE Result_Report SHALL บันทึกวันที่เริ่มทำ POC และหมายเลขเวอร์ชันที่แท้จริงในรูปแบบ major.minor.patch ของ Go, JDK, Spring Boot และไลบรารี PGP ที่ใช้จริงในแต่ละ Runner
4. WHERE ไลบรารี PGP มีหลายเวอร์ชันให้เลือก, THE Result_Report SHALL บันทึกชื่อและหมายเลขเวอร์ชันในรูปแบบ major.minor.patch ของไลบรารี PGP ที่เลือกใช้ในแต่ละภาษา
5. IF หมายเลขเวอร์ชันของ Go, JDK, Spring Boot หรือไลบรารี PGP ที่ใช้ build หรือรันจริงไม่ตรงกับหมายเลขเวอร์ชันที่บันทึกไว้ใน Result_Report, THEN THE Benchmark_Harness SHALL แสดงข้อความแจ้งข้อผิดพลาดที่ระบุว่าเวอร์ชันที่ใช้จริงไม่ตรงกับที่บันทึกไว้ และไม่ถือว่าผลการเปรียบเทียบรอบนั้นเป็นผลที่ถูกต้อง

### Requirement 3: สภาพแวดล้อมการรันต้องเหมือนกัน (Identical Environment)

**User Story:** ในฐานะ Operator ฉันต้องการให้ทั้งสองภาษารันบน VM เดียวกันภายใต้สภาพแวดล้อมเดียวกัน เพื่อให้ความแตกต่างของผลลัพธ์มาจากภาษาและโค้ด ไม่ใช่จากสภาพแวดล้อม

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL รัน Go_Runner และ Java_Runner บน VM อินสแตนซ์เดียวกัน (VM instance ที่มีตัวระบุเดียวกัน) ภายใน Scenario เดียวกัน
2. WHEN Benchmark_Run แต่ละครั้งเริ่มต้น, THE Result_Report SHALL บันทึกข้อมูลสภาพแวดล้อมของ VM ได้แก่ จำนวน vCPU, ขนาด RAM, ระบบปฏิบัติการและเวอร์ชัน, สถาปัตยกรรม CPU และชนิดของ storage
3. WHILE Benchmark_Run กำลังทำงานสำหรับ Runner หนึ่ง, THE Benchmark_Harness SHALL ไม่รัน Runner อื่นพร้อมกันบน VM เดียวกัน โดยอนุญาตให้มี Runner ที่กำลังทำงานอยู่ได้สูงสุด 1 ตัวต่อ VM ในเวลาเดียวกัน เพื่อป้องกันการแย่งทรัพยากร
4. THE Benchmark_Harness SHALL ใช้ค่ากำหนดทรัพยากรเดียวกันสำหรับทั้ง Go_Runner และ Java_Runner ภายใน Scenario เดียวกัน ได้แก่ จำนวน CPU core และโควตา memory ที่อนุญาตให้ใช้ โดยค่าทั้งสองต้องตรงกันทุกประการ (ส่วนต่างเท่ากับ 0)
5. IF VM มีการเปลี่ยนแปลงสเปกหรือค่ากำหนดทรัพยากรระหว่างชุดการทดสอบ เมื่อเทียบกับค่าที่บันทึกไว้ตอนเริ่มต้นชุดนั้น, THEN THE Benchmark_Harness SHALL ทำเครื่องหมายผลลัพธ์ของชุดนั้นว่าไม่สามารถเปรียบเทียบได้ (non-comparable) ใน Result_Report พร้อมข้อบ่งชี้ที่ระบุสาเหตุของการเปลี่ยนแปลง และคงข้อมูลผลลัพธ์ที่เก็บมาแล้วไว้โดยไม่ลบทิ้ง
6. IF Benchmark_Harness ไม่สามารถบันทึกข้อมูลสภาพแวดล้อมของ VM ตามที่ระบุในข้อ 2 ได้ครบถ้วน, THEN THE Benchmark_Harness SHALL ทำเครื่องหมายผลลัพธ์ของ Benchmark_Run นั้นว่าไม่สามารถเปรียบเทียบได้ (non-comparable) ใน Result_Report พร้อมข้อบ่งชี้ที่ระบุว่าข้อมูลสภาพแวดล้อมใดที่ขาดหายไป

### Requirement 4: ใช้ชุดกุญแจ ชุดไฟล์ และค่าตั้งค่า algorithm เดียวกัน

**User Story:** ในฐานะ Operator ฉันต้องการให้ทุกภาษาและทุก variant ใช้ Key_Set, Test_Corpus และ Crypto_Profile เดียวกัน เพื่อให้การเปรียบเทียบยุติธรรม

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL ใช้ Key_Set ชุดเดียวกันสำหรับทุก Runner และทุก Implementation_Variant ภายใน Scenario เดียวกัน
2. THE Benchmark_Harness SHALL ใช้ Test_Corpus ชุดเดียวกัน (ไฟล์เนื้อหาเดียวกันแบบ byte-for-byte) สำหรับทุก Runner และทุก Implementation_Variant ภายใน Scenario เดียวกัน
3. THE Benchmark_Harness SHALL ใช้ Crypto_Profile เดียวกัน (public-key algorithm, symmetric cipher, compression algorithm และ hash algorithm เดียวกัน) สำหรับทุก Runner และทุก Implementation_Variant ภายใน Scenario เดียวกัน
4. IF Runner ใดไม่รองรับค่าใดค่าหนึ่งใน Crypto_Profile ที่กำหนด, THEN THE Benchmark_Harness SHALL บันทึกค่าที่ไม่รองรับนั้นพร้อมระบุ Runner ที่เกี่ยวข้อง และทำเครื่องหมายผลของ Scenario นั้นว่าไม่สามารถเปรียบเทียบได้ (non-comparable) สำหรับ Runner ดังกล่าวใน Result_Report
5. WHEN เริ่ม Benchmark_Run และก่อนเริ่มการ encrypt หรือ decrypt ใด ๆ, THE Benchmark_Harness SHALL คำนวณและบันทึกค่า checksum ของ Key_Set และ Test_Corpus ลงใน Result_Report เพื่อยืนยันว่าทุก Runner ใช้ข้อมูลนำเข้าเดียวกัน
6. IF ค่า checksum ของ Key_Set หรือ Test_Corpus ที่ Runner ใช้จริงไม่ตรงกับค่า checksum อ้างอิงของ Scenario, THEN THE Benchmark_Harness SHALL ยุติ Benchmark_Run ของ Runner นั้น ไม่นำผลการวัดเข้าในสถิติด้านประสิทธิภาพ และรายงานข้อผิดพลาดที่ระบุว่าข้อมูลนำเข้าไม่ตรงกัน
7. THE Benchmark_Harness SHALL กำหนดให้ทุก Runner ใช้รูปแบบการเข้ารหัสผลลัพธ์ (output encoding) แบบเดียวกันภายใน Scenario เดียวกัน กล่าวคือเลือกเป็น binary OpenPGP หรือ ASCII-armored อย่างใดอย่างหนึ่งให้ตรงกันทุก Runner และ THE Result_Report SHALL บันทึก output encoding ที่ใช้ เพื่อให้การเปรียบเทียบขนาด ciphertext (Requirement 18.3, Requirement 30.3) และ interoperability ยุติธรรมและเทียบกันได้

### Requirement 5: ความถูกต้องของการเข้ารหัสและถอดรหัส (Correctness)

**User Story:** ในฐานะ Operator ฉันต้องการให้มั่นใจว่าการ encrypt แล้ว decrypt กลับมาได้ข้อมูลเดิม เพื่อให้ผลการวัดประสิทธิภาพอ้างอิงจากงานที่ทำถูกต้องจริง

#### Acceptance Criteria

1. WHEN Runner ทำ encrypt ตามด้วย decrypt บนแต่ละไฟล์ที่ประมวลผลใน Benchmark_Run, THE Runner SHALL ได้ผลลัพธ์ที่มีขนาดและเนื้อหาเหมือนไฟล์ต้นฉบับแบบ byte-for-byte (round-trip property)
2. IF ผลลัพธ์หลัง round-trip ไม่ตรงกับไฟล์ต้นฉบับ, THEN THE Benchmark_Harness SHALL บันทึกข้อผิดพลาดด้านความถูกต้อง (correctness failure) ที่ระบุไฟล์, Runner, Implementation_Variant และ Benchmark_Run ที่เกี่ยวข้อง และนับรวมเป็นความล้มเหลวใน error rate
3. IF การ decrypt ไม่สามารถทำงานจนเสร็จและไม่ได้ผลลัพธ์สำหรับนำมาเปรียบเทียบ, THEN THE Benchmark_Harness SHALL บันทึกเป็นความล้มเหลวด้านการทำงาน (operation failure) แยกจากกรณีเนื้อหาไม่ตรงกัน และนับรวมใน error rate
4. THE Benchmark_Harness SHALL ตรวจสอบความถูกต้องแบบ round-trip ของทุกไฟล์ใน Benchmark_Run ก่อนนำผลการวัดเวลาของ Benchmark_Run นั้นไปใช้ในการคำนวณค่าสถิติด้านประสิทธิภาพ
5. IF Benchmark_Run ใดมีข้อผิดพลาดด้านความถูกต้อง, THEN THE Benchmark_Harness SHALL ยกเว้นค่าเวลาจากการรันนั้นออกจากการคำนวณค่าสถิติด้านประสิทธิภาพ และรายงานทั้งจำนวน Benchmark_Run ที่ถูกยกเว้นและจำนวนไฟล์ที่ได้รับผลกระทบ

### Requirement 6: หลายรูปแบบการเขียนโค้ดต่อภาษา (Multiple Implementation Variants)

**User Story:** ในฐานะ Operator ฉันต้องการมีหลายรูปแบบการเขียนโค้ด PGP ในแต่ละภาษา เพื่อค้นหาวิธีที่เร็วที่สุดของแต่ละภาษาก่อนนำมาแข่งกัน

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL รองรับการกำหนด Implementation_Variant ได้ตั้งแต่ 2 ถึง 20 รูปแบบต่อภาษา โดยแต่ละ Implementation_Variant มีตัวระบุ (identifier) ที่ไม่ซ้ำกัน
2. THE Go_Runner SHALL มี Implementation_Variant อย่างน้อยสองรูปแบบที่แตกต่างกันในมิติอย่างน้อยหนึ่งมิติจากสองมิติต่อไปนี้: การจัดการหน่วยความจำ (in-memory เทียบกับ streaming) หรือการทำงานขนาน (single-thread เทียบกับ parallel) โดยต้องไม่มีสอง Implementation_Variant ใดที่เหมือนกันทั้งสองมิติ
3. THE Java_Runner SHALL มี Implementation_Variant อย่างน้อยสองรูปแบบที่แตกต่างกันในมิติอย่างน้อยหนึ่งมิติจากสองมิติต่อไปนี้: การจัดการหน่วยความจำ (in-memory เทียบกับ streaming) หรือการทำงานขนาน (single-thread เทียบกับ parallel) โดยต้องไม่มีสอง Implementation_Variant ใดที่เหมือนกันทั้งสองมิติ
4. THE Benchmark_Harness SHALL รัน Implementation_Variant ทุกตัวภายใต้ Scenario เดียวกันด้วย Key_Set, Test_Corpus และ Crypto_Profile เดียวกัน และด้วยจำนวน Round และจำนวน Warm_Up_Iteration ที่เท่ากัน
5. THE Result_Report SHALL รายงานผลการวัดแยกตาม Implementation_Variant แต่ละตัวโดยอ้างอิงด้วยตัวระบุ (identifier) ที่ไม่ซ้ำกันของ variant นั้น
6. IF ภาษาใดมี Implementation_Variant น้อยกว่าสองรูปแบบ, THEN THE Benchmark_Harness SHALL หยุดการทำงานก่อนเริ่ม Benchmark_Run โดยไม่เก็บผลการวัด และรายงานข้อผิดพลาดที่ระบุภาษาที่มี variant ไม่ครบ

### Requirement 7: คัดเลือก Best_Variant ของแต่ละภาษามาแข่งแบบ Head-to-Head

**User Story:** ในฐานะ Operator ฉันต้องการนำ variant ที่ดีที่สุดของแต่ละภาษามาเปรียบเทียบกันโดยตรง เพื่อให้ได้ข้อสรุปที่ยุติธรรมต่อศักยภาพสูงสุดของแต่ละภาษา

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL คัดเลือก Best_Variant ของแต่ละภาษาโดยใช้เกณฑ์เริ่มต้นคือค่า p50 round-trip time ต่ำที่สุด และ SHALL บันทึกเกณฑ์ที่ใช้พร้อมค่าที่ใช้ตัดสินของ variant ที่ถูกเลือกใน Result_Report
2. WHEN Implementation_Variant ทั้งหมดของภาษาหนึ่งรันครบใน Scenario หนึ่งแล้ว, THE Benchmark_Harness SHALL ระบุ Best_Variant ของภาษานั้นสำหรับ Scenario นั้น
3. THE Benchmark_Harness SHALL พิจารณาเฉพาะ Implementation_Variant ที่ผ่านการตรวจสอบความถูกต้องแบบ round-trip ในทุก Benchmark_Run โดยไม่มี correctness error เท่านั้นในการคัดเลือก Best_Variant
4. THE Result_Report SHALL นำเสนอผลการเปรียบเทียบแบบ head-to-head ระหว่าง Best_Variant ของ Go และ Best_Variant ของ Java สำหรับแต่ละ Scenario
5. WHERE ผู้ใช้กำหนดเกณฑ์การคัดเลือก Best_Variant เอง, THE Benchmark_Harness SHALL ใช้เกณฑ์ที่ผู้ใช้กำหนดแทนเกณฑ์เริ่มต้นในการคัดเลือก และบันทึกเกณฑ์ที่ใช้ใน Result_Report
6. IF มี Implementation_Variant มากกว่าหนึ่งตัวที่มีค่าตามเกณฑ์การคัดเลือกเท่ากัน, THEN THE Benchmark_Harness SHALL ตัดสินด้วยลำดับรองคือเลือกตัวที่มีค่า p99 latency ต่ำที่สุด และหากยังเท่ากันให้เลือกตัวที่มีค่าการใช้ RAM สูงสุด (peak RAM) ต่ำที่สุด
7. IF ไม่มี Implementation_Variant ใดของภาษาหนึ่งผ่านการตรวจสอบความถูกต้องแบบ round-trip ใน Scenario หนึ่ง, THEN THE Benchmark_Harness SHALL ทำเครื่องหมายภาษานั้นว่าไม่สามารถเปรียบเทียบได้ (non-comparable) สำหรับ Scenario นั้นใน Result_Report

### Requirement 8: การรันแบบสลับลำดับหลายรอบ (Alternating Execution)

**User Story:** ในฐานะ Operator ฉันต้องการให้รัน Go และ Java สลับกันหลายรอบ เพื่อลด bias จากลำดับการรันและ warm-up และให้ได้ผลที่เสถียรที่สุด

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL รัน Go_Runner และ Java_Runner สลับลำดับกันข้ามหลาย Round โดยภายในแต่ละ Round จะรันทั้ง Go_Runner และ Java_Runner อย่างละหนึ่งครั้ง
2. THE Benchmark_Harness SHALL รองรับการกำหนดจำนวน Round ที่ต้องการโดย Operator เป็นจำนวนเต็มในช่วง 1 ถึง 1,000 Round
3. IF Operator กำหนดจำนวน Round เป็นค่าที่อยู่นอกช่วง 1 ถึง 1,000 หรือไม่ใช่จำนวนเต็มบวก, THEN THE Benchmark_Harness SHALL หยุดการทำงานและรายงานข้อผิดพลาดที่ระบุว่าจำนวน Round ไม่ถูกต้อง
4. WHEN เริ่ม Round แรก, THE Benchmark_Harness SHALL รันตามลำดับเริ่มต้นที่กำหนดไว้ล่วงหน้า (Go_Runner ก่อน Java_Runner)
5. WHEN เริ่มแต่ละ Round หลังจาก Round แรก, THE Benchmark_Harness SHALL สลับลำดับการรันระหว่างสองภาษาให้ตรงข้ามกับลำดับใน Round ก่อนหน้า
6. THE Benchmark_Harness SHALL รัน Warm_Up_Iteration ตามจำนวนที่ Operator กำหนดเป็นจำนวนเต็มในช่วง 0 ถึง 100 ก่อนเก็บผลจริงสำหรับแต่ละ Runner
7. THE Benchmark_Harness SHALL ไม่นับค่าที่วัดได้จาก Warm_Up_Iteration เข้าในการคำนวณค่าสถิติด้านประสิทธิภาพ
8. THE Result_Report SHALL บันทึกลำดับการรันจริงของแต่ละ Round (ระบุว่า Runner ใดรันก่อน-หลัง) และจำนวน Warm_Up_Iteration ที่ใช้จริง เพื่อให้ตรวจสอบย้อนหลังได้

### Requirement 9: เก็บ Metrics ด้านเวลาและ throughput

**User Story:** ในฐานะ Operator ฉันต้องการวัดเวลา encrypt, decrypt, round-trip และ throughput เพื่อเปรียบเทียบประสิทธิภาพเชิงปริมาณ

#### Acceptance Criteria

1. WHEN Runner ทำ encrypt เสร็จในหนึ่ง Benchmark_Run, THE Benchmark_Harness SHALL บันทึกเวลา encrypt เป็น Metric_Record ในหน่วยมิลลิวินาที (ms)
2. WHEN Runner ทำ decrypt เสร็จในหนึ่ง Benchmark_Run, THE Benchmark_Harness SHALL บันทึกเวลา decrypt เป็น Metric_Record ในหน่วยมิลลิวินาที (ms)
3. THE Benchmark_Harness SHALL คำนวณและบันทึกเวลา round-trip ในหน่วยมิลลิวินาที (ms) เป็นผลรวมของเวลา encrypt และ decrypt สำหรับงานเดียวกัน
4. THE Benchmark_Harness SHALL คำนวณและบันทึก throughput เป็นเมกะไบต์ต่อวินาที (MB/sec) โดยใช้ขนาดข้อมูลต้นฉบับ (กำหนดให้ 1 MB เท่ากับ 1,048,576 ไบต์) หารด้วยเวลาที่ใช้ในหน่วยวินาที และคำนวณแยกกันสำหรับ encrypt และ decrypt
5. THE Benchmark_Harness SHALL คำนวณและบันทึก throughput เป็นจำนวนไฟล์ต่อวินาที (files/sec) จากจำนวนไฟล์ที่ประมวลผลสำเร็จและเวลาที่ใช้
6. THE Result_Report SHALL ระบุหน่วยเวลาที่ใช้วัด (มิลลิวินาที) อย่างชัดเจน
7. IF เวลาที่วัดได้สำหรับงานหนึ่งมีค่าน้อยกว่าหรือเท่ากับศูนย์, THEN THE Benchmark_Harness SHALL ไม่คำนวณค่า throughput สำหรับงานนั้น แต่ SHALL คงค่าเวลาที่วัดได้ไว้และทำเครื่องหมายระบุสาเหตุที่ไม่สามารถคำนวณ throughput ได้
8. THE Benchmark_Harness SHALL คำนวณ throughput (ทั้งหน่วย MB/sec และ files/sec) โดยใช้ฐานเวลาเดียวกับ core crypto-time metric (ไม่รวมเวลาการอ่าน/เขียนไฟล์และช่วง warm-up); และ WHERE Scenario รันแบบขนาน (concurrency level มากกว่า 1), THE Benchmark_Harness SHALL นิยาม aggregate throughput เป็นปริมาณข้อมูลรวม (MB) หรือจำนวนไฟล์รวมที่ประมวลผลสำเร็จ หารด้วยช่วงเวลา crypto รวมแบบ wall-clock ของชุดงานขนานนั้น เพื่อกันการตีความ throughput ที่ทำให้ตัวเลขเกินจริง

### Requirement 10: เก็บ Metrics ด้าน latency เปอร์เซ็นไทล์

**User Story:** ในฐานะ Operator ฉันต้องการวัด p95 และ p99 latency เพื่อเข้าใจพฤติกรรมในกรณีแย่ที่สุด ไม่ใช่แค่ค่าเฉลี่ย

#### Acceptance Criteria

1. WHEN งานหนึ่งเสร็จสิ้น, THE Benchmark_Harness SHALL บันทึกเวลาของแต่ละงาน (per-operation latency) แยกกันสำหรับ encrypt และ decrypt โดยไม่นับค่าจาก Warm_Up_Iteration
2. WHEN Benchmark_Run ทั้งหมดของ Scenario เสร็จสิ้น, THE Benchmark_Harness SHALL คำนวณและบันทึกค่า p95 latency และ p99 latency สำหรับ encrypt และ decrypt แยกกัน โดยคำนวณจากเฉพาะงานที่ผ่านการตรวจสอบความถูกต้องแบบ round-trip และไม่นับค่าจาก Warm_Up_Iteration
3. THE Benchmark_Harness SHALL คำนวณและบันทึกค่า latency เฉลี่ย (mean), ค่ามัธยฐาน (p50), ค่าต่ำสุด (min) และค่าสูงสุด (max) สำหรับ encrypt และ decrypt แยกกัน โดยใช้ชุดข้อมูลเดียวกับที่ใช้คำนวณ p95 และ p99
4. THE Result_Report SHALL ระบุวิธีการคำนวณเปอร์เซ็นไทล์ที่ใช้ (formula/interpolation method), จำนวนตัวอย่าง (sample count) ของแต่ละชนิดงาน และหน่วยเวลา เพื่อให้ตีความค่าได้ถูกต้อง
5. IF จำนวนตัวอย่างของงานชนิดหนึ่งน้อยกว่า 20 ตัวอย่างสำหรับการคำนวณ p95 หรือน้อยกว่า 100 ตัวอย่างสำหรับการคำนวณ p99, THEN THE Benchmark_Harness SHALL ทำเครื่องหมายค่าเปอร์เซ็นไทล์นั้นว่าไม่น่าเชื่อถือ (unreliable) ใน Result_Report

### Requirement 11: เก็บ Metrics ด้านการใช้ทรัพยากร (CPU และ RAM)

**User Story:** ในฐานะ Operator ฉันต้องการวัดการใช้ CPU และ RAM เพื่อเข้าใจต้นทุนทรัพยากรของแต่ละภาษา ไม่ใช่แค่ความเร็ว

#### Acceptance Criteria

1. WHILE Benchmark_Run กำลังทำงาน, THE Benchmark_Harness SHALL เก็บตัวอย่างการใช้ CPU ของ Runner ตามช่วงเวลาเก็บตัวอย่าง (sampling interval) ที่กำหนด โดยมีค่าเริ่มต้น 100 มิลลิวินาที และอยู่ในช่วง 10 ถึง 1000 มิลลิวินาที
2. WHILE Benchmark_Run กำลังทำงาน, THE Benchmark_Harness SHALL เก็บตัวอย่างการใช้ RAM ของ Runner ตามช่วงเวลาเก็บตัวอย่างเดียวกับการเก็บ CPU
3. WHEN Benchmark_Run เสร็จสิ้น, THE Benchmark_Harness SHALL บันทึกค่าการใช้ CPU เฉลี่ยและสูงสุดของการรันนั้นเป็นเปอร์เซ็นต์ของ CPU ที่จัดสรรให้ (0 ถึง 100%)
4. WHEN Benchmark_Run เสร็จสิ้น, THE Benchmark_Harness SHALL บันทึกค่าการใช้ RAM เฉลี่ยและสูงสุดของการรันนั้นในหน่วยเมกะไบต์ (MB)
5. THE Result_Report SHALL ระบุหน่วยและวิธีการวัดการใช้ CPU (เปอร์เซ็นต์) และ RAM (MB) ที่ใช้
6. THE Benchmark_Harness SHALL ใช้ช่วงเวลาเก็บตัวอย่าง (sampling interval) เดียวกันสำหรับทั้ง Go_Runner และ Java_Runner ภายใน Scenario เดียวกัน
7. IF การเก็บตัวอย่างการใช้ CPU หรือ RAM ล้มเหลวหรือไม่ครบถ้วนสำหรับ Benchmark_Run หนึ่ง, THEN THE Benchmark_Harness SHALL บันทึกความล้มเหลวพร้อมสาเหตุ และทำเครื่องหมายค่าการใช้ทรัพยากรของการรันนั้นว่าไม่สามารถเปรียบเทียบได้ (non-comparable)

### Requirement 12: เก็บ Metrics ด้าน error rate

**User Story:** ในฐานะ Operator ฉันต้องการวัดอัตราความผิดพลาด เพื่อประเมินความน่าเชื่อถือของแต่ละภาษาควบคู่กับประสิทธิภาพ

#### Acceptance Criteria

1. IF การ encrypt หรือ decrypt ใน Benchmark_Run (ที่ไม่ใช่ Warm_Up_Iteration) ล้มเหลว, THEN THE Benchmark_Harness SHALL บันทึก Metric_Record ที่ระบุสาเหตุของความล้มเหลว, ประเภทความล้มเหลว (operation failure หรือ correctness failure), Runner และ Implementation_Variant ที่เกี่ยวข้อง โดยไม่กระทบผลของ Benchmark_Run อื่น
2. WHEN Scenario เสร็จสิ้น, THE Benchmark_Harness SHALL คำนวณ error rate เป็นอัตราส่วนของจำนวนงาน (operation) ที่ล้มเหลวต่อจำนวนงานทั้งหมดที่พยายามทำหลังเสร็จสิ้น Warm_Up_Iteration โดยไม่นับงานใน Warm_Up_Iteration และรายงานเป็นค่าทศนิยมในช่วง 0.0 ถึง 1.0
3. THE Result_Report SHALL รายงาน error rate แยกตาม Runner และตาม Implementation_Variant พร้อมแสดงจำนวนงานที่ล้มเหลวและจำนวนงานทั้งหมดที่พยายามทำที่ใช้ในการคำนวณ
4. THE Benchmark_Harness SHALL นับทั้งความล้มเหลวด้านการทำงาน (operation failure) และความล้มเหลวด้านความถูกต้อง (correctness failure) เป็นงานที่ล้มเหลวในการคำนวณ error rate
5. IF จำนวนงานทั้งหมดที่พยายามทำ (หลัง Warm_Up_Iteration) ใน Scenario เท่ากับศูนย์, THEN THE Benchmark_Harness SHALL รายงาน error rate ของ Scenario นั้นว่าไม่สามารถคำนวณได้ (not applicable) แทนการคำนวณอัตราส่วน

### Requirement 13: Scenario ตามขนาดไฟล์ที่หลากหลาย (Edge Case)

**User Story:** ในฐานะ Operator ฉันต้องการทดสอบกับไฟล์หลายขนาด เพื่อดูว่าแต่ละภาษาเหมาะกับไฟล์เล็กหรือไฟล์ใหญ่ต่างกันอย่างไร

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL รองรับ Scenario ที่กำหนดขนาดไฟล์อย่างน้อยสามระดับ ได้แก่ ขนาดเล็ก (1 KB ถึง 1 MB), ขนาดกลาง (มากกว่า 1 MB ถึง 100 MB) และขนาดใหญ่ (มากกว่า 100 MB ถึงอย่างน้อย 1 GB)
2. THE Benchmark_Harness SHALL รองรับ Scenario ที่ประกอบด้วยไฟล์ขนาดเล็กจำนวนมาก (many small files) โดยมีจำนวนไฟล์อย่างน้อย 1,000 ไฟล์ และแต่ละไฟล์มีขนาดไม่เกิน 1 MB เพื่อวัดผลของ overhead ต่อไฟล์
3. THE Result_Report SHALL รายงาน metrics แยกตามแต่ละระดับขนาดไฟล์ที่กำหนดใน Scenario โดยไม่นำค่าจากระดับขนาดที่ต่างกันมารวมเป็นค่าเดียว
4. WHERE Operator กำหนดระดับขนาดไฟล์เพิ่มเติมที่มีค่าขนาดมากกว่า 0 ไบต์, THE Benchmark_Harness SHALL รวมระดับขนาดไฟล์นั้นเข้าในชุดการทดสอบและรายงาน metrics ของระดับนั้นแยกต่างหาก
5. IF Operator กำหนดระดับขนาดไฟล์ที่มีค่าไม่ถูกต้อง (เช่น น้อยกว่าหรือเท่ากับ 0 ไบต์ หรือไม่ใช่ค่าตัวเลข), THEN THE Benchmark_Harness SHALL ปฏิเสธระดับขนาดไฟล์นั้น ไม่รวมเข้าในชุดการทดสอบ และรายงานข้อผิดพลาดที่ระบุระดับขนาดไฟล์ที่มีปัญหา

### Requirement 14: Scenario ตามชนิดและขนาดของกุญแจ (Edge Case)

**User Story:** ในฐานะ Operator ฉันต้องการทดสอบกับกุญแจหลายชนิดและหลายขนาด เพื่อดูผลของ algorithm กุญแจต่อประสิทธิภาพของแต่ละภาษา

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL รองรับ Scenario ที่ใช้กุญแจต่างชนิดกันอย่างน้อยสองชนิด ครอบคลุมกุญแจแบบ RSA และกุญแจแบบ elliptic-curve เป็นอย่างน้อย
2. THE Benchmark_Harness SHALL รองรับ Scenario ที่ใช้กุญแจ RSA อย่างน้อยสองระดับขนาดบิต ครอบคลุมกุญแจขนาด 2048 บิต และ 4096 บิต เป็นอย่างน้อย
3. THE Benchmark_Harness SHALL ใช้กุญแจที่มีชนิดและขนาดบิตเดียวกัน (จาก Key_Set ชุดเดียวกัน) สำหรับทุก Runner และทุก Implementation_Variant ภายใน Scenario เดียวกัน
4. THE Result_Report SHALL รายงาน metrics โดยจำแนกแต่ละผลลัพธ์ด้วยป้ายกำกับชนิดกุญแจ (เช่น RSA หรือ elliptic-curve) และขนาดบิตของกุญแจอย่างชัดเจน เพื่อให้แยกผลตามชนิดและขนาดของกุญแจได้
5. IF Runner ใดไม่รองรับชนิดหรือขนาดกุญแจที่กำหนดใน Scenario, THEN THE Benchmark_Harness SHALL บันทึกความไม่รองรับนั้นพร้อมระบุชนิดและขนาดบิตของกุญแจที่ไม่รองรับ, ทำเครื่องหมาย Scenario นั้นว่าไม่สามารถเปรียบเทียบได้ (non-comparable) สำหรับ Runner ดังกล่าวใน Result_Report, และ SHALL ดำเนินการ Scenario ต่อไปสำหรับ Runner อื่นที่รองรับโดยไม่หยุดชุดการทดสอบทั้งหมด

### Requirement 15: Scenario โหมด streaming เทียบกับ in-memory (Edge Case)

**User Story:** ในฐานะ Operator ฉันต้องการเปรียบเทียบการประมวลผลแบบ streaming กับแบบ in-memory เพื่อดูว่าแต่ละแนวทางส่งผลต่อความเร็วและการใช้หน่วยความจำอย่างไร

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL รองรับ Implementation_Variant แบบ in-memory (โหลดทั้งไฟล์เข้าหน่วยความจำก่อนประมวลผล)
2. THE Benchmark_Harness SHALL รองรับ Implementation_Variant แบบ streaming (ประมวลผลข้อมูลเป็นช่วง ๆ โดยที่การใช้หน่วยความจำสูงสุด (peak memory) ไม่เพิ่มขึ้นตามขนาดของไฟล์)
3. THE Result_Report SHALL รายงานเวลา encrypt, เวลา decrypt, เวลา round-trip และค่าการใช้ RAM เฉลี่ยและสูงสุด แยกตามโหมด streaming และ in-memory และแยกตามระดับขนาดไฟล์
4. IF ไฟล์ที่ทดสอบมีขนาดใหญ่กว่าโควตา memory ที่กำหนดให้ Runner ใน Scenario, THEN THE Benchmark_Harness SHALL ใช้ Implementation_Variant แบบ streaming สำหรับงานนั้น
5. IF Implementation_Variant แบบ in-memory ใช้หน่วยความจำเกินโควตาที่กำหนด (out of memory) ระหว่างประมวลผล, THEN THE Benchmark_Harness SHALL บันทึกความล้มเหลวพร้อมสาเหตุ, นับรวมใน error rate, ทำเครื่องหมายผลของ variant นั้นว่าไม่สามารถเปรียบเทียบได้ (non-comparable), และดำเนินการส่วนที่เหลือของ Scenario ต่อไป

### Requirement 16: Scenario การทำงานแบบขนาน (Concurrency/Parallelism) (Edge Case)

**User Story:** ในฐานะ Operator ฉันต้องการทดสอบการประมวลผลแบบขนานหลายระดับ เพื่อดูว่าแต่ละภาษาขยายงานตามจำนวน core ได้ดีเพียงใด

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL รองรับ Scenario ที่กำหนดระดับการทำงานขนาน (concurrency level) เป็นจำนวนเต็มบวกตั้งแต่ 1 ถึงจำนวน vCPU ของ VM ได้อย่างน้อยสองระดับ คือ ระดับ single-thread (concurrency level เท่ากับ 1) และระดับ multi-thread (concurrency level มากกว่าหรือเท่ากับ 2)
2. THE Benchmark_Harness SHALL ใช้ระดับการทำงานขนาน (concurrency level) ค่าเดียวกันสำหรับทั้ง Go_Runner และ Java_Runner ภายใน Scenario เดียวกัน
3. THE Result_Report SHALL รายงาน throughput (ทั้งหน่วย MB/sec และ files/sec) และค่าการใช้ CPU เฉลี่ยและสูงสุด แยกตามระดับการทำงานขนานแต่ละระดับ
4. WHERE Operator กำหนดระดับการทำงานขนานเป็นจำนวนเท่ากับจำนวน vCPU ของ VM, THE Benchmark_Harness SHALL รองรับการรันที่ระดับนั้น
5. IF Operator กำหนดระดับการทำงานขนานที่ไม่ถูกต้อง (น้อยกว่า 1, ไม่ใช่จำนวนเต็ม, หรือมากกว่าจำนวน vCPU ของ VM), THEN THE Benchmark_Harness SHALL หยุดการรัน Scenario นั้น, ไม่บันทึกผลการวัดของ Scenario นั้นเข้าในสถิติด้านประสิทธิภาพ และรายงานข้อผิดพลาดที่ระบุระดับการทำงานขนานที่มีปัญหา

### Requirement 17: ควบคุมผลของ GC และ JIT warm-up (Edge Case)

**User Story:** ในฐานะ Operator ฉันต้องการลดและบันทึกผลกระทบจาก garbage collection และ JIT warm-up เพื่อให้การเปรียบเทียบยุติธรรมต่อ runtime ที่มีพฤติกรรมต่างกัน

#### Acceptance Criteria

1. WHEN เริ่ม Benchmark_Run, THE Benchmark_Harness SHALL รัน Warm_Up_Iteration ตามจำนวนที่ Operator กำหนด (อย่างน้อย 1 ครั้ง) ก่อนเก็บผลจริงสำหรับทุก Runner และ SHALL ไม่นับค่าจาก Warm_Up_Iteration เข้าในชุดสถิติด้านประสิทธิภาพ
2. WHILE Benchmark_Run กำลังทำงาน, THE Benchmark_Harness SHALL เก็บข้อมูลกิจกรรม garbage collection ของทั้ง Java_Runner และ Go_Runner ได้แก่ จำนวนครั้งและเวลารวมที่ใช้ใน garbage collection ในหน่วยมิลลิวินาที
3. THE Result_Report SHALL บันทึกค่าตั้งค่า runtime ที่เกี่ยวข้อง ได้แก่ ชนิด garbage collector, ขนาด heap เริ่มต้นและสูงสุดที่กำหนดให้ Java_Runner และค่า GC target percentage รวมถึงสถานะเปิด/ปิด GC ของ Go_Runner
4. THE Benchmark_Harness SHALL รายงานค่าสถิติประสิทธิภาพเป็นสองชุดที่มีป้ายกำกับแยกกันอย่างชัดเจน คือ ชุดที่รวม Warm_Up_Iteration และชุดที่ไม่รวม Warm_Up_Iteration
5. IF ไม่สามารถเก็บข้อมูล garbage collection ของ Runner ใดได้, THEN THE Benchmark_Harness SHALL บันทึกความไม่พร้อมใช้งานของข้อมูลนั้นพร้อมสาเหตุ และดำเนินการ Benchmark_Run ต่อไป

### Requirement 18: Scenario ค่าตั้งค่า cipher และ compression (Edge Case)

**User Story:** ในฐานะ Operator ฉันต้องการทดสอบค่าตั้งค่า symmetric cipher และ compression ที่ต่างกัน เพื่อดูผลต่อความเร็วและขนาดผลลัพธ์ของแต่ละภาษา

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL รองรับ Scenario ที่กำหนด symmetric cipher ได้อย่างน้อยสองแบบที่แตกต่างกันภายใน Crypto_Profile
2. THE Benchmark_Harness SHALL รองรับ Scenario ที่ทดสอบทั้งสถานะเปิด compression และสถานะปิด compression แยกกัน เพื่อเปรียบเทียบผล
3. THE Result_Report SHALL รายงานทั้งเวลาในการประมวลผลและขนาดของข้อมูลที่เข้ารหัส (ciphertext size) ในหน่วยไบต์ แยกตามแต่ละ symmetric cipher และแต่ละสถานะ compression
4. THE Benchmark_Harness SHALL ใช้ค่าตั้งค่า symmetric cipher และ compression เดียวกันสำหรับทุก Runner ภายใน Scenario เดียวกัน
5. IF Runner ใดไม่รองรับค่า symmetric cipher หรือค่า compression ที่กำหนดใน Scenario, THEN THE Benchmark_Harness SHALL บันทึกค่าที่ไม่รองรับนั้น, ทำเครื่องหมาย Scenario นั้นว่าไม่สามารถเปรียบเทียบได้ (non-comparable) สำหรับ Runner ดังกล่าว และคงผลของ Runner อื่นไว้

### Requirement 19: ความสามารถในการทำซ้ำและการตั้งค่า (Reproducibility & Configuration)

**User Story:** ในฐานะ Operator ฉันต้องการให้การทดสอบทำซ้ำได้และตั้งค่าได้จากที่เดียว เพื่อให้ผู้อื่นรันซ้ำและได้ผลที่เทียบเคียงกันได้

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL อ่านพารามิเตอร์การทดสอบทั้งหมด ได้แก่ จำนวน Round, จำนวน Warm_Up_Iteration, รายการ Scenario, Crypto_Profile, ระดับ concurrency และค่า seed จากไฟล์ตั้งค่าเดียว
2. WHEN Benchmark_Run เริ่มทำงาน, THE Benchmark_Harness SHALL บันทึกค่าตั้งค่าทั้งหมดที่ใช้จริง (ค่าทุกพารามิเตอร์ตามข้อ 1 พร้อมค่าที่ได้รับจริง) ลงใน Result_Report
3. WHEN Benchmark_Run เริ่มทำงาน, THE Benchmark_Harness SHALL บันทึกวันที่ เวลา และเขตเวลา (timezone) ของจุดเริ่มต้นของชุดการทดสอบลงใน Result_Report
4. WHEN Benchmark_Run สิ้นสุดการทำงาน, THE Benchmark_Harness SHALL บันทึกวันที่ เวลา และเขตเวลา (timezone) ของจุดสิ้นสุดของชุดการทดสอบลงใน Result_Report
5. WHERE Operator ระบุค่า seed สำหรับการสร้างข้อมูลทดสอบ, THE Benchmark_Harness SHALL ใช้ค่า seed นั้นเพื่อให้สร้าง Test_Corpus เดิมซ้ำได้แบบ bit-for-bit เมื่อรันด้วย seed และพารามิเตอร์ชุดเดียวกัน
6. IF ไฟล์ตั้งค่ามีค่าพารามิเตอร์ไม่ถูกต้อง (อยู่นอกช่วงที่กำหนดหรือผิดชนิดข้อมูล) หรือขาดพารามิเตอร์ที่จำเป็นตามข้อ 1, THEN THE Benchmark_Harness SHALL หยุดการทำงานก่อนเริ่ม Benchmark_Run โดยไม่สร้าง Result_Report และรายงานข้อผิดพลาดที่ระบุชื่อพารามิเตอร์ที่มีปัญหาและสาเหตุของปัญหา

### Requirement 20: รายงานผลและข้อสรุป (Reporting & Conclusion)

**User Story:** ในฐานะ Operator ฉันต้องการรายงานสรุปที่อ่านเข้าใจง่ายและข้อสรุปว่าภาษาใดเหมาะกว่า เพื่อใช้ตัดสินใจ

#### Acceptance Criteria

1. WHEN ชุดการทดสอบทั้งหมดเสร็จสิ้น, THE Benchmark_Harness SHALL สร้าง Result_Report ภายใน 60 วินาที ที่รวม Metric_Record ทั้งหมดของทุก Runner ทุก Implementation_Variant และทุก Scenario
2. THE Result_Report SHALL นำเสนอการเปรียบเทียบแบบ head-to-head ระหว่าง Best_Variant ของ Go และ Best_Variant ของ Java โดยแสดงค่าสถิติ (ค่าต่ำสุด, ค่าสูงสุด, ค่าเฉลี่ย, ค่ามัธยฐาน, p95 และ p99) สำหรับแต่ละ metric ด้านเวลา throughput latency การใช้ทรัพยากร และ error rate
3. THE Result_Report SHALL ระบุข้อสรุปว่าภาษาใดเหมาะสมกว่าสำหรับ workload PGP encrypt/decrypt โดยใช้เกณฑ์การตัดสินที่กำหนดไว้ล่วงหน้าและลำดับความสำคัญของ metrics ที่ระบุไว้ พร้อมเหตุผลอ้างอิงจากข้อมูล
4. IF ผลต่างของ metric ที่ใช้ตัดสินระหว่าง Best_Variant ของสองภาษามีค่าน้อยกว่าหรือเท่ากับ 5%, THEN THE Result_Report SHALL ระบุว่าผลการเปรียบเทียบไม่ชี้ขาด (inconclusive) แทนการสรุปว่าภาษาใดเหมาะกว่า
5. THE Result_Report SHALL จัดเก็บผลทั้งในรูปแบบที่อ่านด้วยโปรแกรมได้ (machine-readable) และรูปแบบที่อ่านเข้าใจง่ายสำหรับมนุษย์ (human-readable) อย่างละอย่างน้อยหนึ่งรูปแบบ
6. WHERE ผลของบาง Scenario ถูกทำเครื่องหมายว่าไม่สามารถเปรียบเทียบได้ (non-comparable), THE Result_Report SHALL ระบุ Scenario เหล่านั้นพร้อมเหตุผลอย่างชัดเจน และ SHALL ไม่นำผลเหล่านั้นเข้าในการคำนวณข้อสรุป
7. IF การสร้าง Result_Report ล้มเหลวหรือไม่มีข้อมูลที่เปรียบเทียบได้เลย, THEN THE Benchmark_Harness SHALL แสดงข้อความแจ้งข้อผิดพลาดต่อ Operator และคงข้อมูลผลการวัดที่เก็บมาแล้วไว้โดยไม่ลบทิ้ง

### Requirement 21: วัดแยกโหมด Cold Start และ Steady State

**User Story:** ในฐานะ Operator ฉันต้องการวัดประสิทธิภาพแยกระหว่างโหมด cold start และโหมด steady-state เพื่อให้ข้อสรุปไม่เอนเอียงตามวิธีวัด และสะท้อนทั้ง workload แบบ process สั้นและ service ที่รันยาว

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL รองรับการวัดทั้งโหมด Cold_Start และโหมด Steady_State สำหรับทั้ง Go_Runner และ Java_Runner
2. WHEN วัดในโหมด Cold_Start, THE Benchmark_Harness SHALL รัน encrypt/decrypt ให้จบภายใน process เดียว และนับรวม Process_Startup_Time และเวลา JIT warm-up เข้าในผลการวัดของโหมดนั้น
3. WHEN วัดในโหมด Steady_State, THE Benchmark_Harness SHALL เก็บผลการวัดหลังจากรัน Warm_Up_Iteration จนครบตามที่กำหนดแล้วเท่านั้น โดยไม่นับ Process_Startup_Time และเวลา JIT warm-up เข้าในผลการวัดของโหมดนั้น
4. WHEN Runner เริ่มต้น process ในโหมด Cold_Start, THE Benchmark_Harness SHALL บันทึก Process_Startup_Time แยกเป็น Metric_Record ต่างหากในหน่วยมิลลิวินาที (ms)
5. THE Result_Report SHALL รายงานผลการวัดแยกตามโหมด Cold_Start และโหมด Steady_State โดยไม่นำค่าจากสองโหมดมารวมเป็นค่าเดียว
6. IF Runner ใดไม่สามารถวัดในโหมด Cold_Start หรือโหมด Steady_State ที่กำหนดได้, THEN THE Benchmark_Harness SHALL บันทึกสาเหตุที่วัดไม่ได้ และทำเครื่องหมายผลของโหมดนั้นสำหรับ Runner ดังกล่าวว่าไม่สามารถเปรียบเทียบได้ (non-comparable) ใน Result_Report
7. THE Result_Report SHALL รายงานเวลา Cold_Start ทั้งหมด (รวม Process_Startup_Time และเวลา JIT warm-up) เป็น metric เสริมที่มีป้ายกำกับแยกต่างหาก โดยไม่นำมารวมเข้าใน core crypto-only steady-state statistics ตาม Requirement 1

**เหตุผล (Rationale):** ถ้า workload จริงเป็น process สั้น (CLI/batch/serverless) เวลา JVM startup และ JIT warm-up มีผลมหาศาลและมักทำให้ Go ชนะ แต่ถ้าเป็น service ที่รันยาว Java จะตามทันหลัง warm-up การวัดแยกสองโหมดจึงกันข้อสรุปที่เอนเอียงตามวิธีวัด

### Requirement 22: GraalVM Native Image เป็น Java Variant เพิ่มเติม

**User Story:** ในฐานะ Operator ฉันต้องการมี Java variant ที่ compile เป็น native binary เพื่อให้ "ตัวเก่งที่สุดของ Java" ได้แข่งกับ Go อย่างยุติธรรมโดยลบจุดอ่อนเรื่อง startup และ warm-up

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL รองรับ Native_Image_Variant ของ Java ที่ถูก compile เป็น native binary เพิ่มเติมจาก Implementation_Variant แบบ JVM
2. THE Benchmark_Harness SHALL จัดให้ Native_Image_Variant เข้าร่วมการคัดเลือก Best_Variant ของ Java ภายใต้ Key_Set, Test_Corpus และ Crypto_Profile เดียวกับ Implementation_Variant อื่นของ Java
3. WHEN build Native_Image_Variant, THE Result_Report SHALL บันทึกชื่อและหมายเลขเวอร์ชันในรูปแบบ major.minor.patch ของ build toolchain ที่ใช้สร้าง native binary
4. THE Result_Report SHALL รายงานผลการวัดของ Native_Image_Variant แยกจากผลการวัดของ Implementation_Variant แบบ JVM โดยระบุป้ายกำกับว่าเป็น native หรือ JVM อย่างชัดเจน
5. IF การ build Native_Image_Variant ล้มเหลว, THEN THE Benchmark_Harness SHALL บันทึกสาเหตุของความล้มเหลว, ไม่นำ Native_Image_Variant นั้นเข้าในการคัดเลือก Best_Variant และดำเนินการ Scenario ต่อไปด้วย Implementation_Variant ที่ build สำเร็จ

**เหตุผล (Rationale):** เพื่อให้ "ตัวเก่งที่สุดของ Java" แฟร์จริง การลบจุดอ่อนเรื่อง startup และ warm-up ด้วย native image ทำให้ Java แข่งกับ Go ได้สูสีขึ้นมาก

### Requirement 23: บันทึกและทดสอบ Hardware Acceleration (AES-NI / CPU Crypto Instructions)

**User Story:** ในฐานะ Operator ฉันต้องการรู้ว่าแต่ละ Runner ใช้ hardware crypto acceleration จริงหรือไม่ เพื่อให้มั่นใจว่าความต่างของผลมาจากภาษาและโค้ด ไม่ใช่จากการที่ฝั่งหนึ่งได้ accel แต่อีกฝั่งไม่ได้

#### Acceptance Criteria

1. WHEN Benchmark_Run เริ่มต้น, THE Result_Report SHALL บันทึกว่าแต่ละ Runner ใช้ Hardware_Acceleration (เช่น AES-NI) ในส่วน symmetric cipher จริงหรือไม่ เป็นค่าระบุได้แน่นอน (ใช้/ไม่ใช้)
2. THE Benchmark_Harness SHALL รองรับ Scenario ที่ใช้ cipher ที่ได้รับ Hardware_Acceleration (เช่น AES-GCM) และ Scenario ที่ใช้ cipher ที่โดยทั่วไปไม่ได้รับ Hardware_Acceleration (เช่น ChaCha20) แยกกัน
3. THE Result_Report SHALL รายงานผลการวัดแยกตามสถานะการใช้ Hardware_Acceleration และแยกตามชนิด cipher ที่ใช้ใน Scenario
4. IF สถานะการใช้ Hardware_Acceleration ของ Go_Runner และ Java_Runner ไม่ตรงกันภายใน Scenario เดียวกัน, THEN THE Benchmark_Harness SHALL ทำเครื่องหมายผลการเปรียบเทียบของ Scenario นั้นว่าไม่สามารถเปรียบเทียบได้ (non-comparable) พร้อมข้อบ่งชี้ที่ระบุความไม่ตรงกันนั้นใน Result_Report

**เหตุผล (Rationale):** ส่วน bulk ของ PGP เป็น symmetric cipher ที่ CPU เร่งได้ด้วย AES-NI ถ้าไลบรารีฝั่งหนึ่งใช้ accel แต่อีกฝั่งไม่ใช้ ผลจะต่างกันหลายเท่าโดยไม่เกี่ยวกับภาษาเลย

### Requirement 24: แยกเวลา Asymmetric กับ Symmetric

**User Story:** ในฐานะ Operator ฉันต้องการเห็น breakdown ของเวลาระหว่างส่วน asymmetric และส่วน symmetric เพื่อเข้าใจว่าภาษาใดเก่งตรงส่วนไหนของงาน hybrid แบบ PGP

#### Acceptance Criteria

1. WHERE ไลบรารี PGP ของ Runner เปิดให้วัดเวลาแยกส่วนได้, THE Benchmark_Harness SHALL วัดและบันทึกเวลาส่วน asymmetric (การเข้ารหัส/ถอดรหัส session key ด้วย RSA หรือ ECC) แยกจากเวลาส่วน symmetric (การเข้ารหัส/ถอดรหัสเนื้อข้อมูล) เป็น Metric_Record ในหน่วยมิลลิวินาที (ms)
2. THE Result_Report SHALL รายงาน breakdown ของเวลาส่วน asymmetric และส่วน symmetric แยกกันสำหรับ encrypt และ decrypt เมื่อมีข้อมูลการวัดดังกล่าว
3. IF ไลบรารี PGP ของ Runner ใดไม่เปิดให้วัดเวลาส่วน asymmetric และ symmetric แยกกันได้, THEN THE Benchmark_Harness SHALL บันทึกว่าไม่มีข้อมูล breakdown สำหรับ Runner นั้นพร้อมสาเหตุ และคงการวัดเวลารวม (round-trip) ของ Runner นั้นไว้ตามปกติ

**เหตุผล (Rationale):** PGP เป็น hybrid ไฟล์เล็กเวลาหมดไปกับ asymmetric ส่วนไฟล์ใหญ่หมดไปกับ symmetric การวัดรวมอย่างเดียวมองไม่เห็นว่าภาษาใดเก่งตรงส่วนไหน

### Requirement 25: ทดสอบ Cross-Language Interoperability

**User Story:** ในฐานะ Operator ฉันต้องการพิสูจน์ว่าทั้งสองฝั่งสร้าง OpenPGP ที่ถูกต้องตามมาตรฐานจริง เพื่อกันเคสที่ฝั่งหนึ่งเร็วเพราะ implement ไม่ครบสเปก

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL ทำ Interoperability_Check โดยตรวจสอบว่า ciphertext ที่ Go_Runner สร้างขึ้นสามารถถูกถอดรหัสได้โดย Java_Runner และให้ผลลัพธ์ตรงกับไฟล์ต้นฉบับแบบ byte-for-byte
2. THE Benchmark_Harness SHALL ทำ Interoperability_Check โดยตรวจสอบว่า ciphertext ที่ Java_Runner สร้างขึ้นสามารถถูกถอดรหัสได้โดย Go_Runner และให้ผลลัพธ์ตรงกับไฟล์ต้นฉบับแบบ byte-for-byte
3. WHERE มีเครื่องมือมาตรฐาน OpenPGP (เช่น gpg CLI) พร้อมใช้งานในสภาพแวดล้อม, THE Benchmark_Harness SHALL ตรวจสอบว่า ciphertext ที่แต่ละ Runner สร้างขึ้นสามารถถูกถอดรหัสได้ด้วยเครื่องมือมาตรฐานนั้น
4. THE Result_Report SHALL บันทึกผลของ Interoperability_Check แต่ละคู่เป็นค่า pass หรือ fail พร้อมระบุทิศทางของการตรวจสอบ (Runner ที่สร้างและ Runner หรือเครื่องมือที่ถอดรหัส)
5. IF Interoperability_Check คู่ใดได้ผลเป็น fail, THEN THE Benchmark_Harness SHALL บันทึกความล้มเหลวพร้อมระบุคู่ที่เกี่ยวข้องและสาเหตุ และทำเครื่องหมายผลการเปรียบเทียบที่เกี่ยวข้องว่าไม่สามารถเปรียบเทียบได้ (non-comparable) ใน Result_Report

**เหตุผล (Rationale):** การตรวจสอบนี้พิสูจน์ว่าทั้งสองฝั่งสร้าง OpenPGP ที่ถูกต้องตามมาตรฐานจริง ไม่ใช่แค่ถอดรหัสของตัวเองได้ จึงกันเคสที่ฝั่งหนึ่งเร็วเพราะ implement ไม่ครบสเปก

### Requirement 26: ความเข้มงวดทางสถิติ (Statistical Rigor)

**User Story:** ในฐานะ Operator ฉันต้องการตัวเลขทางสถิติที่บอกความเชื่อมั่นของผล เพื่อกันการสรุปจาก noise และให้ข้อสรุปเชื่อถือได้

#### Acceptance Criteria

1. WHEN Scenario เสร็จสิ้น, THE Benchmark_Harness SHALL คำนวณและบันทึกค่าเบี่ยงเบนมาตรฐาน (standard deviation) และ Coefficient_Of_Variation (CV) สำหรับ latency ของ encrypt และ decrypt แยกกัน เพิ่มเติมจากค่า p95 และ p99
2. WHERE Operator กำหนดเกณฑ์ความเสถียร (stability threshold) เป็นค่า CV สูงสุดที่ยอมรับได้, THE Benchmark_Harness SHALL หยุดเก็บผลเพิ่ม (stop) เมื่อค่า CV ที่วัดได้ต่ำกว่าหรือเท่ากับเกณฑ์ที่กำหนด
3. WHEN Result_Report สรุปว่าภาษาใดเร็วกว่าอีกภาษาหนึ่ง, THE Result_Report SHALL รายงานช่วงความเชื่อมั่น (confidence interval) หรือค่า effect size ประกอบข้อสรุปนั้น
4. THE Result_Report SHALL ระบุระดับความเชื่อมั่น (confidence level) และวิธีการคำนวณทางสถิติที่ใช้ เพื่อให้ตีความผลได้ถูกต้อง
5. IF จำนวนตัวอย่างไม่เพียงพอต่อการคำนวณช่วงความเชื่อมั่นหรือ effect size อย่างมีความหมาย, THEN THE Result_Report SHALL ทำเครื่องหมายข้อสรุปนั้นว่าไม่น่าเชื่อถือ (unreliable) พร้อมระบุจำนวนตัวอย่างที่ใช้

**เหตุผล (Rationale):** ผลต่างเล็กน้อยอาจไม่มีนัยสำคัญทางสถิติ การมี CV และช่วงความเชื่อมั่นช่วยกันการสรุปจาก noise และทำให้ข้อสรุปเชื่อถือได้

### Requirement 27: ควบคุม Noise ของเครื่อง (Machine Noise Control)

**User Story:** ในฐานะ Operator ฉันต้องการควบคุมและบันทึกตัวแปรกวนของเครื่อง เพื่อแยก noise ของเครื่องออกจากความต่างที่แท้จริงระหว่างภาษา

#### Acceptance Criteria

1. WHEN Benchmark_Run เริ่มต้น, THE Result_Report SHALL บันทึกค่าตั้งค่าที่กระทบความเสถียรของเครื่อง ได้แก่ สถานะ CPU turbo boost (เปิด/ปิด), CPU governor ที่ใช้ และชนิดของ storage ที่ใช้เก็บ Test_Corpus
2. THE Benchmark_Harness SHALL รองรับการวาง Test_Corpus บน ramdisk หรือ tmpfs เพื่อตัดผลของ disk I/O ออกจากการวัด
3. WHILE Benchmark_Run กำลังทำงาน, THE Benchmark_Harness SHALL เฝ้าระวัง thermal throttling ของ CPU และบันทึกเหตุการณ์ thermal throttling ที่ตรวจพบลงใน Result_Report
4. THE Benchmark_Harness SHALL รองรับ null test ที่รัน Runner ชนิดเดียวกันแข่งกับตัวเอง (Go_Runner เทียบ Go_Runner หรือ Java_Runner เทียบ Java_Runner) เพื่อวัด Noise_Floor ของ Benchmark_Harness
5. THE Result_Report SHALL รายงานค่า Noise_Floor ที่วัดได้จาก null test เพื่อใช้เป็นฐานเทียบกับผลการเปรียบเทียบระหว่างสองภาษา
6. IF ตรวจพบ thermal throttling ระหว่าง Benchmark_Run, THEN THE Benchmark_Harness SHALL ทำเครื่องหมายผลของ Benchmark_Run ที่ได้รับผลกระทบว่าไม่สามารถเปรียบเทียบได้ (non-comparable) พร้อมข้อบ่งชี้ที่ระบุช่วงเวลาที่เกิด throttling

**เหตุผล (Rationale):** frequency scaling, disk I/O และ thermal throttling เป็นตัวแปรกวนที่ทำให้ผลไม่นิ่ง การควบคุมและ null test ช่วยแยก noise ของเครื่องออกจากความต่างของภาษา

### Requirement 28: มุมต้นทุนและพลังงาน (Cost & Energy)

**User Story:** ในฐานะ Operator ฉันต้องการมุมตัดสินใจเชิงธุรกิจด้านต้นทุน พลังงาน และขนาด deploy เพื่อสะท้อนต้นทุนจริงนอกเหนือจากความเร็วล้วน

#### Acceptance Criteria

1. WHERE สภาพแวดล้อมรองรับการวัดพลังงาน, THE Benchmark_Harness SHALL วัดหรือประมาณพลังงานต่อ operation ในหน่วยจูล (joules) หรือ throughput ต่อกำลังไฟในหน่วยต่อวัตต์ (per watt) สำหรับแต่ละ Runner
2. THE Benchmark_Harness SHALL คำนวณและบันทึกต้นทุนต่อ 1 ล้าน operation โดยคิดจากค่า vCPU ที่ใช้สำหรับแต่ละ Runner
3. WHEN Benchmark_Run เสร็จสิ้น, THE Result_Report SHALL บันทึกขนาดของ binary หรือ container image และค่าการใช้ RAM ขณะ idle ในหน่วยเมกะไบต์ (MB) ของแต่ละ Runner
4. THE Result_Report SHALL รายงานค่าต้นทุน พลังงาน ขนาด deploy และ memory ขณะ idle แยกตาม Runner เพื่อใช้ประกอบการตัดสินใจ
5. IF สภาพแวดล้อมไม่รองรับการวัดพลังงาน, THEN THE Benchmark_Harness SHALL บันทึกว่าไม่มีข้อมูลพลังงานพร้อมสาเหตุ และยังคงรายงานค่าต้นทุนต่อ operation, ขนาด deploy และ memory ขณะ idle ตามปกติ

**เหตุผล (Rationale):** ผู้บริหารต้องการมุมตัดสินใจเชิงธุรกิจ ตัวเลขต้นทุน พลังงาน และขนาด deploy สะท้อนต้นทุนจริงนอกเหนือจากความเร็วล้วน

### Requirement 29: Soak / Endurance Test

**User Story:** ในฐานะ Operator ฉันต้องการทดสอบการรันต่อเนื่องเป็นเวลานาน เพื่อตรวจหา memory leak, การถดถอยของประสิทธิภาพ และพฤติกรรม GC ระยะยาว ซึ่งสำคัญต่อ service ที่รันต่อเนื่อง

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL รองรับ Soak_Test ที่กำหนดเป็นระยะเวลาการรันต่อเนื่องหรือจำนวน operation รวมตามที่ Operator กำหนด
2. WHILE Soak_Test กำลังทำงาน, THE Benchmark_Harness SHALL เก็บตัวอย่างค่า latency และค่าการใช้ RAM เป็นช่วงเวลาตลอดระยะเวลาการรัน เพื่อใช้วิเคราะห์แนวโน้ม
3. WHEN Soak_Test เสร็จสิ้น, THE Result_Report SHALL รายงานแนวโน้มของ latency และค่าการใช้ RAM ตลอดช่วงเวลา รวมถึงข้อมูลกิจกรรม garbage collection ระยะยาวของแต่ละ Runner
4. IF ค่าการใช้ RAM ของ Runner ใดมีแนวโน้มเพิ่มขึ้นอย่างต่อเนื่องเกินเกณฑ์ที่กำหนดตลอด Soak_Test, THEN THE Benchmark_Harness SHALL ทำเครื่องหมายว่าตรวจพบ memory leak ที่น่าจะเกิดขึ้น (suspected memory leak) สำหรับ Runner นั้นใน Result_Report พร้อมข้อมูลแนวโน้มประกอบ
5. IF ค่า latency ของ Runner ใดมีแนวโน้มถดถอย (เพิ่มขึ้น) อย่างต่อเนื่องเกินเกณฑ์ที่กำหนดตลอด Soak_Test, THEN THE Benchmark_Harness SHALL ทำเครื่องหมายว่าตรวจพบการถดถอยของประสิทธิภาพ (performance degradation) สำหรับ Runner นั้นใน Result_Report พร้อมข้อมูลแนวโน้มประกอบ

**เหตุผล (Rationale):** ปัญหา memory leak และการถดถอยของ GC จะโผล่เฉพาะตอนรันยาว (เช่น ZGC กับ G1 ต่างกันชัดในงานยาว) ซึ่งสำคัญต่อ service ที่รันต่อเนื่อง

### Requirement 30: ลักษณะข้อมูลที่ต่างกัน (Data Compressibility)

**User Story:** ในฐานะ Operator ฉันต้องการทดสอบทั้งข้อมูลที่บีบอัดได้และบีบอัดไม่ได้ เพื่อกันการสรุปจากข้อมูลชนิดเดียว เพราะผลของ compression ต่างกันมากตาม compressibility ของข้อมูล

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL รองรับ Scenario ที่ใช้ข้อมูลบีบอัดได้ (เช่น ไฟล์ข้อความ) และ Scenario ที่ใช้ข้อมูลบีบอัดไม่ได้ (เช่น ไฟล์สุ่มหรือไฟล์ที่บีบอัดมาแล้ว) แยกกัน
2. THE Benchmark_Harness SHALL ใช้ข้อมูลชนิดเดียวกัน (compressibility เดียวกัน) สำหรับทุก Runner และทุก Implementation_Variant ภายใน Scenario เดียวกัน
3. THE Result_Report SHALL รายงานเวลาในการประมวลผลและขนาดของข้อมูลที่เข้ารหัส (ciphertext size) ในหน่วยไบต์ แยกตามชนิดข้อมูลที่บีบอัดได้และบีบอัดไม่ได้
4. IF Operator กำหนดชนิดข้อมูลที่ไม่ถูกต้องหรือไม่สามารถสร้างได้, THEN THE Benchmark_Harness SHALL ปฏิเสธชนิดข้อมูลนั้น ไม่รวมเข้าในชุดการทดสอบ และรายงานข้อผิดพลาดที่ระบุชนิดข้อมูลที่มีปัญหา

**เหตุผล (Rationale):** ผลของ compression ต่อเวลาและขนาด ciphertext ต่างกันมากตาม compressibility ของข้อมูล การทดสอบทั้งสองแบบจึงกันการสรุปจากข้อมูลชนิดเดียว

### Requirement 31: การสร้างชุดกุญแจ (Key_Set Generation)

**User Story:** ในฐานะ Operator ฉันต้องการให้ระบบสร้าง Key_Set ที่ครอบคลุมกุญแจ RSA-2048 และ RSA-4096 ไว้ล่วงหน้าและใช้ร่วมกันทั้งสองภาษา เพื่อให้การทดสอบยุติธรรมและทำซ้ำได้

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL สร้าง Key_Set ที่ประกอบด้วยกุญแจคู่ (public/private key pairs) ทั้งแบบ RSA ขนาด 2048 บิต และ RSA ขนาด 4096 บิต สำหรับใช้ในการ encrypt และ decrypt
2. THE Benchmark_Harness SHALL ใช้ Key_Set ชุดเดียวกันที่สร้างขึ้นร่วมกันสำหรับทั้ง Go_Runner และ Java_Runner และทุก Implementation_Variant ภายใน Scenario เดียวกัน สอดคล้องกับข้อกำหนดใน Requirement 4
3. WHEN สร้าง Key_Set, THE Benchmark_Harness SHALL บันทึกข้อมูลที่ทำให้ทำซ้ำได้ของกุญแจแต่ละคู่ลงใน Result_Report ได้แก่ ชนิดกุญแจ ขนาดบิต และ fingerprint หรือตัวระบุ (identifier) ของกุญแจ
4. IF การสร้าง Key_Set ล้มเหลว หรือไม่สามารถสร้างกุญแจตามชนิดหรือขนาดบิตที่กำหนดได้, THEN THE Benchmark_Harness SHALL หยุดการทำงานก่อนเริ่ม Benchmark_Run และรายงานข้อผิดพลาดที่ระบุชนิดและขนาดบิตของกุญแจ (key spec) ที่สร้างไม่สำเร็จ

**เหตุผล (Rationale):** กุญแจที่ใช้ต้องถูกสร้างไว้ล่วงหน้าและใช้ร่วมกันทั้งสองภาษาเพื่อความยุติธรรมและการทำซ้ำได้ การบันทึก fingerprint และ key spec ทำให้ตรวจสอบย้อนหลังได้ว่าทุก Runner ใช้กุญแจชุดเดียวกันจริง

### Requirement 32: ชนิดไฟล์ที่รองรับและกฎการตั้งชื่อไฟล์นำเข้า/ผลลัพธ์

**User Story:** ในฐานะ Operator ฉันต้องการให้ระบบรองรับชนิดไฟล์จริงตามที่ใช้งานในระบบ พร้อมกฎการตั้งชื่อไฟล์ผลลัพธ์และการข้ามไฟล์ที่ไม่ต้องเข้ารหัส เพื่อให้การทดสอบสะท้อนพฤติกรรมการใช้งานจริง

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL รองรับการ encrypt ไฟล์ชนิด .txt, .xlsx, .xls, .csv, .pdf, .zip, .7z, .dat และ .gz
2. WHEN encrypt ไฟล์ชนิดที่รองรับ, THE Runner SHALL ตั้งชื่อไฟล์ผลลัพธ์โดยต่อท้ายนามสกุลเดิมด้วย .pgp (เช่น report.pdf เป็น report.pdf.pgp)
3. IF ไฟล์เป็นชนิด .ctrl หรือ .ctl, THEN THE Runner SHALL ไม่เข้ารหัสไฟล์นั้น (ข้าม/skip) และบันทึกว่าไฟล์นั้นถูกข้ามใน Result_Report
4. WHERE ไฟล์เป็น zip ที่บรรจุไฟล์หลายชนิด, THE Runner SHALL เข้ารหัสทั้ง zip เป็นไฟล์เดียวที่มีนามสกุล .zip.pgp
5. WHEN decrypt, THE Runner SHALL คืนไฟล์กลับเป็นชนิดและเนื้อหาต้นฉบับแบบ byte-for-byte สอดคล้องกับ round-trip property ใน Requirement 5
6. THE Result_Report SHALL รายงาน metrics แยกตามชนิดไฟล์ (เช่น .txt, .pdf, .csv, .xlsx) โดยไม่นำค่าจากชนิดไฟล์ที่ต่างกันมารวมเป็นค่าเดียว
7. IF พบไฟล์ชนิดที่ไม่อยู่ในรายการที่รองรับและไม่ใช่ชนิดที่ระบุให้ข้าม (.ctrl หรือ .ctl), THEN THE Benchmark_Harness SHALL ข้ามไฟล์นั้นพร้อมบันทึกเหตุผลว่าเป็นชนิดไฟล์ที่ไม่รองรับลงใน Result_Report

**เหตุผล (Rationale):** รองรับชนิดไฟล์จริงตามที่ใช้งานในระบบ และ rule การตั้งชื่อ/ข้ามไฟล์ที่ไม่ต้องเข้ารหัส สะท้อนพฤติกรรมการใช้งานจริง รวมถึงผลของ compressibility ที่ต่างกันตามชนิดไฟล์
