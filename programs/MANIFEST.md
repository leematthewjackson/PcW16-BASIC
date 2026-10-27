# Prebuilt programs

These are the PcW16 executables and pictures the project owner ran in the XAnne emulator (Rosanne 1.12) in the sessions that accepted M14. The third column says what that session recorded; none has been run on a real PcW16 yet. Each `.PRG` was built from the source named, with the options shown, and the compiler in this repository builds it byte for byte the same: `python3 tools/verify_public.py` rebuilds every one and compares it with the file here. SPRITED, MDEDIT IV, DESIGNER and SCICALC are built from their M14 versions (`examples/*_m14.pbas`), which correct the known issues KI-96, KI-97, KI-99 and KI-104. Copy a program together with the pictures it loads ([docs/running-in-xanne.md](../docs/running-in-xanne.md)).

| file | built from | in XAnne | SHA-256 |
|---|---|---|---|
| PAINT2.PRG | examples/paint2.pbas --runtime-banks all | passed in XAnne (M14) | `a695a4d28fccb96fd5f4acfac2e67f6a1e6d02aea51c2231b4a1971765dbe963` |
| P2ICONS.PBI | examples/assets (P2ICONS.PBI) | a picture for the program listed before it | `fee416826e222a796af4ba13f130039bf5b8dbd2b98b1d9927435a3e84422e15` |
| DESIGNER.PRG | examples/designer_m14.pbas --runtime-banks all | passed in XAnne (M14) | `2f36bb3c431013b9a88679d0bcd1cd442ecd4767702d5aad8c22dafc807a6bcd` |
| JUMPER.PRG | examples/jumper.pbas --runtime-banks all | passed in XAnne | `e1739f94859d56969351a080001d564705c4c2b2affe542a54a04371b26d7868` |
| JHERO.PBI | examples/assets (JHERO.PBI) | a picture for the program listed before it | `9cc32e6a138668fb28d01cbfe5cf5932298eba20c1c944c519368ee48d028890` |
| JHEROM.PBI | examples/assets (JHEROM.PBI) | a picture for the program listed before it | `7aabfb486d95542f63111dc5579190acd49dbd1296b1f9f03bc91fbc92e38f86` |
| JBUG.PBI | examples/assets (JBUG.PBI) | a picture for the program listed before it | `8064ce55cb093a351089b6112706cc5138b2d694e2fefea425f1ff837bd6e366` |
| JBUGM.PBI | examples/assets (JBUGM.PBI) | a picture for the program listed before it | `1f7d12c8c9c2372ba9b57ef63b414df9583ff53266d7fca7a59fd2e5be5925ef` |
| JCOIN.PBI | examples/assets (JCOIN.PBI) | a picture for the program listed before it | `30a9014b920010cc61fa0e430aa8337c8f9a8fd59c084f4d7f7928ae2cffedad` |
| JCOINM.PBI | examples/assets (JCOINM.PBI) | a picture for the program listed before it | `6f8ef47b445d3fda380d2ad1d9fd03eedb10ceebcf4decd3193957f08bb6b001` |
| SPRITED.PRG | examples/sprited_m14.pbas --runtime-banks all | passed in XAnne (M14) | `a0b3dcc03bf4b5afdad17cbae8380da973a0831434a461c225aa989e996c293c` |
| T1HELLO.PRG | examples/tutorial/t1_hello.pbas | no XAnne run recorded | `31d8e33aba629e13928a248389e946b46682d0c62ab7d06b90fb66dcaf732ed4` |
| T2DRAW.PRG | examples/tutorial/t2_draw.pbas | no XAnne run recorded | `376afb432e7beb24daa70b62091f033090cb32c8fff64545b6da4873e61ed28d` |
| T2ICONS.PBI | examples/assets (T2ICONS.PBI) | a picture for the program listed before it | `07223131c2ad59aabd2fcd0fb967e56bc01786382522b35ae2b2dcf8ddec094c` |
| T3HOP.PRG | examples/tutorial/t3_hop.pbas | passed in XAnne | `22859971b9d92382c05dd60ffefcb4b8fc1c2790781d7b27bbe3a6260bbca2d6` |
| T3HERO.PBI | examples/assets (T3HERO.PBI) | a picture for the program listed before it | `f9479ac254632331e8471d009702f141d5b249ff82b7873211bff67a3bd5b434` |
| T3HEROM.PBI | examples/assets (T3HEROM.PBI) | a picture for the program listed before it | `d8bdfef6bcc47fca8c0ad505c8a862b863fb844b922ac965e3d21b9155738203` |
| MDEDIT4.PRG | examples/mdedit4_m14.pbas --runtime-banks all | passed in XAnne (M14) | `4e18be44e48605ff62d72f42d62134ea90199132f6b780b3c9ca4917ec4f31f8` |
| SCICALC.PRG | examples/scicalc_m14.pbas | passed in XAnne (M14) | `2b4fb81dbf9ea892a9256064a52e3908f774aaf2c5636750919a392893967a18` |
