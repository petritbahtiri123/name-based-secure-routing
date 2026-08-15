from __future__ import annotations

import base64
import hashlib
import json
import zlib
from collections.abc import Mapping
from enum import IntEnum
from types import MappingProxyType
from typing import Any


REGISTRY_SOURCE_SHA256 = "ed880f236a2b4b5e11e281e58c540534e1cd27f7c752d3990291cf1be55c80d0"
_REGISTRY_SOURCE_B85 = (
    b"c%1EBU31$wvVG65VEOfi<HU9{$!y&RMP?H2D3XSfob{dBV!<RNV?&V~kg}uMn*V;Q0T2W!e#tgyJEOcLp-6l*4o){3jmCdp7{<{u"
    b"qHC18H<%_Q3Xgs<UcZFLF^!faz(>CrN8wdM%_a6RMJb6w)5kaF&FdrfT9Tr4lfYXjj%jp*efSv%QM|@sYG$RdcW(*B?vi5sCltFx"
    b"L4w(H6a<mSigx2DAl?>=8w7z7kR-*vaf5;lP7Fk`kyT=x=am>!UWt*Hll)|iqYxV;F^~~sx<(<q_)+%3fVL<f7@II9fsuIEc#RSR"
    b"g}!lvy)>e{T8eK7zQz7eydxB^NRm>5q2vF3VHk#Sgukaa1PQvthsVFO$A<Wsy%M4|ljle4+;RqUdopIliC<YSGx3XO9i=Ni_>2Ah"
    b"Z~py}hhlU^0+Md`X^}hm@K0+vpFMEPUUsT`u$X_IIQIY5%H~8%3+B#XJev+2YdpMkr_N;Zv9kN8S}LE-2XlMq&Yi_<?hYqkrh~ct"
    b"!5-Q3%c?e<=^ldNWIVV2HFrPQ<8yobsj3Zc^bEph$C`bfjLu!_!aldgL#wLpw+}QqqO1R4FLl#xj9aG0BnHZesKe*{*1=vx{r;xM"
    b"uXsDyq}LH8e=?@3uV2sP7^5|w+=iGY*Cej5T+ie<#{piobX(Jukg8%%H%a<o6Z%4p^)nkN3X>R79D3W~HTJ&65ed@=o)Hc8+o2b1"
    b"K$}fz6fLXj{aH)B!zfHZ>4)C7w&r(QYW_;n5GTnjMJa}Ft7?9)rRI!btk7qp+`ureG-F*bO<FJf*RT6&0w=p+6sGul<ygGdWD9I#"
    b">^t~I*o6&ap@;E?QMe3<ms&T($DvnAIj_&O;&4Qk*xPymZs@!o)`JRfFx@itBQ5fOt5yCEPNHDb(gZymIEZ76f^+PVq`CTc4`d9j"
    b"agv}F?qUsnw9eh(U^-wHs%=#-6W*S_(`Kg@YIg_2U+Y?+2ceTG7|IjJb*$mUId^|sSk7f#6W;dH1jm|9C*zq_*9tu#wZ`Yui9Mco"
    b"62!Y+n$RW)P1^hG*m7o{?P<1ponJNz<Nd4Nn$aSV_j*)$UO!t(Hw)vWmnO6cLXRrvOZpFs@%hMd9qYG+HJjJ9;H-}pGz;O4{w6G@"
    b"=Yx4|1K#RyK)t?ruW3E=*&6=JS*md!ywhEK+vw{dM|(UREoR_X$|hpNEI51hs;5RYiQ?>)9$Fku#xr|1&wY$-!Z_)z8O`F*LylkV"
    b"`PiDxTyTF{U#xMh81yh>!PDF}5^s8GLh~r-AxFo$m<)LXri<C<y2^jnU3o1ppS^mgyY2>FK6~|EckM0XuF2ywoQyw?>>;Ry>BOl6"
    b"z9wIfth|2IH92?W(g|2+F>4%pP5zy76WYdK5B>eN7&wFR+#Xx*crv$#wbg6#^H{^lh2>nfRIZEjtnu8rY}{so+JDx)djDk4=1vy{"
    b"bRS309h%Y%$oIWCHJVlmXD6?EY(oP}ooL$evo4D};qG+tVPw~;=aZA3n$aMM)1I2pjEl2gThSyBJ-j&{e6ifz)6)Wrw|%ssK?Xnf"
    b"QGYWa-u2gnCQ0bw%yVmGed<CGr>}I^U*GrB*ShO&M8N4uKh-x$;ItR-cMAm0dTB(16yEgGfMzhf?Xe9_viMo|qHZ=BExHiHyWSeo"
    b"APqh2IG9eY!KlTuK6|CN?nYDk?4cq(DMm>Yx?beBZQqV3<I2|P5rgG`Ej^nooT258>@RlpFleiLI&i9mf1<6*F@#VK#*?u<9E|#l"
    b"lY^=k<Jn>g-W=E@ckFpx3p8m0$8m?w<#av)xAI4OR4I5(O2Bd4nf+-zm@gd5wZ|8Ok$v7@tQ=Giu7r6_%&w*lc*k*JWinkj(@8bV"
    b"-)XIQWPh}Vm&59Tey?w!ho7x4gC3*fpwbJ=feoY{1LB}oxsBap{2LeXWLmAX^s(1;GO~x4uJy0!U|cI|ebnVlMxzgPHi|yha;)iS"
    b"P~(BtR;l&d!p`;|dJJo08e#%Y=S3Z)^$`~Axcq8WDg{j*O{jHlIbZDYV8nMhD=iUyoTZ*>sjONbapiFbl@)7buIb30yBD_gwX$M;"
    b"^p$OA%Tp|s_3PuWk5DbNpt4?l1eR^0xL@qqtmeFsCPySxKUvHNpDdv~D(lwAW#^Nx<4?}uyn0^iqq5OtI2bi`Ss$OteY*x5Ta&Yq"
    b"8QJ5x<&10ARS&h8{)V@1yrFTFv@NDHo8NUNlO9*L*&y_{uoe4*mu!($Gs%0}0P1f+TXgdGx0uac%l)lj)fmbCR<MO*x1-6Y9?yDl"
    b"ZQbL-HFFW4+q3%FtLu2z9tW&7t!DFpryiHGpFq&#L0yQ)scvC&eAk6nX^LwcPQm567|ol=TGxtp49jQ;=Iqjjw-2bWgY3v!oB!MT"
    b"SC5){Fr3>LJvyKrYi>Ke>StDC^|D$Iz8lu@ZypFwkvIm~8B~MmbY$1~7PJWA!gB17b{4m5)h22<(O7$RfAyej>P#+da0>Rhp;141"
    b"^^oUmF@vG3mg`&1QJ|HT>WccVH-O&tO;UQSz0B=5x@`12>aq453-b5WRQYf_&itUZo1|#f#*fl#&_Gpsm&$GvXPsz`GIp%l+_CEh"
    b"<n+PDBiRI<(%CS-jgH(?P5cc(DD~#Qo&l(h?boBD9?475xCyH_c)veAmBkbFr=)lQ&jYKd!i@DrdIvY!q+YacwK0c7Yuc-m5wu8u"
    b"v$a7r=vuin@v`nyH#*lZI9x{5V>yi6^-~K8JGaJ{?%4Y3E^5N!Gz~V;GkEKVb^EY-dg~1AN@Z}W)9z%kr?7ab6Y|*uAq{2OqFgUP"
    b"N$Y-zJYVxj8z+VHJ^k*WoLd*xXfhS9F@D<0=?@sY9^gK+OLp<|zv<i0ulsOJf3}L)FzPV^P(<`*^Qpgu^|>{h1HrL8wGFlFKQ*1j"
    b"wfDG(Qg4&$J}sT?UiG+*G9NgfEXapDp2MC(^?Z7LZ$<V(v;r2;nBHLDr6}YMjh3{|+24k$F;3pR5&!;ow^Yn|DL=QDQj@bbFGG!F"
    b"t1F}~*PBwx+p{yJPp{v;J$+wURL!x2yd?GTRb6{(!Y!2MbdXH#7EoTy+Ya(=bo?tV>d>uv2U%XuS(joe{W^IW9Y(xqrMZ`Unidv$"
    b"L2ud%YO)&@F*lVYC$1M!?0QiU@IJ;YZ>gNUKqpCzJnYg9&t<QqfX}nIvmEapqLg6Yh{9lNkT4-WHstI#>~rHaOA8<38%zxnrkKVQ"
    b"Lwb6Y7{iESLrkrg2A`-ejffhU(uj%#_B?q!jH+mhEZu}O^nuA=GZDomtHp%QiKp4OtiKic=Xu8dH1eV#OXaWrXn^)|EcccBx@2FA"
    b"$0uO>mWg?XEtKNcBqZz2x>VX4eb1i$yi*zzhUANV%6h+3R*4Lc*a+~4d^i&vU=N1pYHN5wlwe<E_doV{QrVYA7^Ma>!p#~};)#zl"
    b"RBXAX_)8UgCJiwnIcR08B{N8^C?~l@vz%#?*rb&vXLD}A<i<o!JGsuyHDEql@{M&d1lhF9Z*Y)3VcJgZh?=^S9Z@S%2}%CL@=*U`"
    b"q;!MjB;17G!ss^Sg30f25R*{w&W>A2D3A{4mzZ+Lu6GU1_0_v0fKB2!AUJW;Na;ug$4Kauw6T1?OO!cscc?G_sbC<;$0e0icrNu_"
    b"%{;3HdH%FQPstw(N?CbYR7c7Wih?OoYeH5brfx3DHA*S@o)2tIYJ7!~L=g#2)#;*IeCkkjSt$e0aq+c8CK|?3dQEY19R+@&ZU$}j"
    b"J;UHAR~1ZwY?|7;yTmNEu=4l%hAE~6{5h>|Sf&eeNJr}{60*6?EZ`t8LFOjKe{2ZFev!;-t`xY}xV1WWiehPatB+A@as`zUR`r7J"
    b"0gOTn1862FCCL)>d|?2q?qs;v=vDeHih`((hkbw{yC<G^Zi&z>i^>??o}gRd?&+s-dt=tTCF!-9cu|at<5hjP#=Qou#lu;YP))dV"
    b"ql^?c2mE>S_tF?O*OA<7$Qs<j<>6|2@sYWwbWzIRK_Z?6fC+s>>4sucbmUK*fU7N97NxXvt;^q4PDw7PDmm?3LUS)UJuuVsGM{QL"
    b"!+99nw8D{Hlt|+_ji;jEbvIInqAy)6bg$v8-+n5}sl&OK-iEYs-|8`%-8RTH3b2{P*dt5gwTx=<uBOA-K6bP3YwT5Cfu#&93Q|m="
    b"xSN6(v?Qf$D=$TKg;Nu}t~3e)OpBeZ!$`TjUCB4?5$=k<@(5b1z$=7a7JO0o>Hri5K@3Egq!f{`qO(T{T4Pg4OCi&)sLbRY!hODh"
    b"nfK{|#NE2YdN_%f7F*>7S5Y2&NxZul@fy<=7_6p`!>tLsLeEf=C)y-g#BQ~Wn6o_$qtrycZ${L_-(wW|W(v#x@|$A2$2@)Y%1p2q"
    b"g}(55?agoaJMz*1+JjAnt8%Y5-y7m@tJ_eKkKHA~OqNGfGN9@LkNm=weC!jFxC{)w*cVZLzd-@<VebND<7RtOuG*@dZ?fGKR+ro~"
    b"Ij-F!d7+9$S#cHb5$r`RS01^2ii%iQL-)3wt5-keD;R&6EtPwkCbbttKFs>?k#+-KKC?mmQN5hCcYodsUCmL0_oXEzi0EngrMo%I"
    b"?>S<XSEb%-w05E_4+C_k0m>sQqbPMLjswKwCzQC5ERG?IPEeYd2hx;c*<?g#76he!mB-2yz9ONIV;uVM)h+k178b5Gm7ySD$Z=)Y"
    b"R8tKE5z}Z*670JXbyG~&Bt(JBI=n_(W)qfTRn{a)NVsxgF-*dZ7}$V>7_G2*MKStD!j+i`gj>{7lrbeY$lJP6j6)Kxa!GdNn?@j4"
    b"A|;PrDo92M(XIOAwEB}P0`|NTpyNgBHAxvF%JD8fSz%>;a0K$lN$L{65Ya+n0wXG6r2dS*$Asd<Md?wY86f=tyBj71WiXeB1RILo"
    b"+E}IRg<{N7dHHsPHa<zqfRO{}<0YmP`)(F$qy!p&oxU@9Zd(&_mcxm4n9b&^*9Ah8QO;LE<N;XnKC>r9o;#YO<ePD#u2|TU)14=0"
    b"J5S#1Jb8Px!v<MTT^|SJ22*s!LmT->npay>gw?HZh!c_=Z(>*u8QFILBZJ2kvFOTxq?n>Wgz6bL*h?d-#4DvJ`Sw~)eOMxG0vP5X"
    b"h;Db*Um2bt7|Me=Dpq3=RX$+Tv!GO9B*qix%K*+$nSAL}I}ALuun<rsYzMg#H94Nmn1mtr&1;gR5hW1tnM51vVUukXVc#U7vP5M+"
    b"xoZ@XB}|52j3YntlH)AM^Ei(IJ-&_KnQ?$ZAO%ro^3#6+ra5bGD22%)W88ofzq`O;0Zy^Yzbdj7d=_970;8?P8!idsO<E^!<#hrD"
    b"!|WC-=%T#k7p2!2gt6~lafMeqB~0)l1SrMS1VorCl;Rzfpk<1wd%ans(B)?WP>|0^RY%Ei$P8EI5JqUe@C96<gs_oM@EV0F@iNT^"
    b"y^vwL+>PgY(S~Wfa1#Vlg;4?r4YHr!i0IEeRv8M<V>QiEl<?6`tFwkEWU_NjyMo;%T9bguHxGm~(TZZOo~00Puem|w-(Z@O1SbZd"
    b"1*POFz=je=E!%g@r`xeOYH^$we|!~fLSKYI8*E&R^jeA01qFto4+#FpVtGZB?oX=MCiF2a5nSO*QxRK?F|Fb&4+Br#uM`$i%4lx6"
    b"RQ%aT%*@#`?ap^XN(Co4VFQ`M^3|gxR>aLiT-O^u6G|9RMvA>xbhRB3AFtzxZLc$Af+Lx?g}L4F_moW-4~0?4h(|Dzco9NC^TNbb"
    b"b!9j?tC8V_g`=OC*|0I`n1wD@#;z77Kp{34FPGS3f(oOsym?r{FuOwJ?l^|U9ii)l0gv%=4W6ZQkSQdJc}V#tOg3>GQNX8133N9w"
    b"<ji~8C`I1414gxAw0vbCPdZWw(#%XXeUgafP8p&Ow{sIC3Nwgi4nZS}u{QW3*MKeeXp<V49baH0&;~+bZDb8m%{w0_saVwIzjuXY"
    b"rZr7CLPtE@fW$vGg?_hTk&RsfQVBiG;30IL07nxt*<kgJzN+Z}0TPUsYJpc5NPkZ-%Ik;jj>mLELzOXMVM={C*d*4XW`dU3KvxNj"
    b"kijCFjAg{NJ6HN_$lIXV4xt+C-5b*qniMB-6ehSIblzY}mIMRhyz57z%AUb$Zo-rVVm)Yzr5K2#0OImxY7LBvMTpoP88wSA%NUiL"
    b"r5RET*fvW^y3Or@1HV3Zek}zR?#ZuZXg2d}Cv<Xt&0aM;6#8ttI59lBjnimFQG5;Z3buky(};1aaEZZjRnfNt#r}8{yDwh5QLJ)#"
    b"Z|1&iqFGs)Niq1Fz>8ALvr_K^GP4s(Y$4^#Lpp|cjY!DM1fXSsM}vht9XR&6a%{z!wEx*Tn6<A(TY=PO*6jvXPP-^aD)li{5qrFY"
    b")@;4CqOjr*SB9(!4wwt?_rcEnfk^ma04*q)fvA>|b97Ig$>d`<Hs;4i8ZBPt;PO({yCnnh4Hk*dSXfL1<BBksItscvUv;tZT^(Hq"
    b"YOX|b?J<l!>9`Eju2fuy)ZDv}o3j~Yxhp~1yd+J;`Yqea_XzIE?RwzeXM|Y6w+ueDe5)P+mN$e~f|x}rn^)|FvYBi{ubyxbw_tsP"
    b"zio&tJm4%tMu=}QRW}^OuTOj9;J~LX=v2?I?@6X53^p-o7Z6r)sQ@CZzVd)01B;08rwzS+sZu&#GATb#vfK-ff+<CZJ5l9gdJYFu"
    b"?+DWACb@>~|BMVXnP)hKC6)?Qz-_7|9(X3m<q=K?+&&@P)<zDrgLdG-VVnT_E1bw>K7%GVM`Id!uwx#s3=un+Z_WO(LCjSkKVt}I"
    b"=kws?kAXZ7$0>U9h~6uH;689hxv*K%)*xE_=!nj+!J5s(1#?J=7RxYT<*0(ZVY|s$pt5JH^_r)vFi^^@R<<FQIR{dTv5}BJd%|j="
    b"=|QwQSgHGhu_kBFo@S~7v^FEP9c$%q0)A>zMP3#=&?#!59V0)8QL1E;c}{eAR|HC*sqA%~mbb^l(E@G;lpd+ZwR~qbBw1D`BU&o4"
    b"10t543z4xTI9X*gpByuarQm@Z%g8Kc?b?$QcTx9n#F%YK6+@{C@MG)w&Y=6-kR*5cJtuzL7loaCo5RU?X3yp<<=MlMqL(LeGp=xY"
    b"i*abAw^0^Mohxy$5)&Rh9YtwRUit$q-XD-VY5Mjx7Avr)iyFNs3?VKrT$Oi_BoJGXci_e!2#TH9QJj%>XY;|_f@BJJ1?F^f6%gUi"
    b"6vtr=)@N{B$k?VGY6Mb@=n91*X<8dXMbX-UDVyFmGDQcU6*hOWbaut2JTKiA3Bt3&HEV7etszs2^73l+x3XDn6h0B29_5(4!S}q4"
    b"yqU%|N{nRVc^LcH-#0L%D}49fPw!EYgJ{4fR}kH^!tDdcfk==xsrc?F%@w^0)a<}=G5lHJE6c70$MhHyr0<<4oB-os2gz;Ny;tN?"
    b"EASu56sQ@79n3v502eclHo_Pts>z7XRERD+f)AZi2fmJ<^Gtm1bTRu}jrlxtT>Ty>bO~Uay~#`lvR-4Kz?P^&ykIhjGblIMP;R1m"
    b"+M7o4Cb{n0n8?NXta!OP;c8c-Lg{n|)Yfi=Hh{LU2b#O1`1U0WpBBfYi-_hjd};8MDKAy%zT~I|xfxu%PaDjK9Z-Ex?!M`%z_?-4"
    b"vjNDzZ7{p;Ph>+;!OF47qM<{9Z=S=0Ar-RMbUS2y2-y2EP`PXMD(GuAc^d$jS-BYicdP&o!@Bd;&m#cpv7B57?O(eikR^nJ)WJ15"
    b"R7CE}3dlm%lf<AnMFe*1A={C}YebDC4oGU=5PU1~DVJfJP(4y|LquMctV{jiIP033=jO^*LFu*;$I$bhP@J_f6XCOh@J_PncJyAs"
    b"2|Xs?YOK~L`>6wJ!AfONh`I9S+FW8&?A~V(1qTE8b(mqB72XESJt1|lMxPTdvyi-+>?*Kzu$Xm9^&>B6t+hnO27xdKWbz65p<;Q8"
    b"bW}W-02m6Zp6r0b+31Hl&tFdKzNZCRhG548KlLcAjmXRKCo=x<6a3vz-rf12^K&ygrKFw}G2R)F!s^U>U1xOuwiq~r@!TF;?szh{"
    b"hj$0*I7;CdV`9L7B@mGJ#|H6J`1y)RkRwkjt9qKGp7$t5k8p7Ru6Pck6sqZoN};aD)9$+<_}?5p=Ndp<tK_r$9UdODNICB$m3S(z"
    b"v5+uD;O6H*6|af(sGSx}2blH?(+n^FkQv*VT_&HqQ)_%~k3YfPNAlT)<=7wX24L6Ta&j+ZTVuEo#JYg1*Y5%C*(QzyfHs81T+=9v"
    b"WO=ECxq#0<a}m5W)=@|x<8`>=ZhwlAPguZ=WN+}hGReWOCJxhfM(*9V%^KUkTZ_r#kv#)@fuBRov1W6}9?tb3U7QgR3Cvjr@cN8b"
    b"d1g$0b5477jqGm>fnHuqXpP8jZwNT?^%_JgQuzor7FgO=hWyTqF57`%+Ic8Ubzr;KK$;xdB2n4jDEp-fkiFsBX|>mkSCMc~By&~3"
    b"nx91l@`f%m?uMNR9{1F7pZ3lcNEe_#(rQok>3K!V+y$!Hp1zvGyAGQy31(ADfKHg4Qk=le2?hc~Axc3~nHxg-!-N+?Tpm(R6wq~B"
    b"OlMZW$2s-?_ajg)=PuN#z_Wfgp%X-F;$I{>1uU~;fuXNv1?Y)358DNg1I_NyE5BNo#Y?~4>Egr4t_vdkhPTbUsT@Ga%ujK@m&s#g"
    b"zu|2$&bza%3CFfz$to{q(?FQ4Z~cb|K10U*6>kgSt`D0Hco&wnWZ4GE8lKG1xr4_8O+HJSybB)hLz7J=<~}T$o0q#tq!Aw<Sn%YV"
    b"UtF<2DcU^PnNO58+bqpHk|#j*U|$}Hvz<7{gD;kwXH0K2E@h(gj^vrCaJZvT$?IS6aBdm@?Xz12rJ1a>gMs<PGMzsZPnJMgzYgyN"
    b"$O1=-MYsf`@}bI)OgP%;u?fNlg47PgJF{b>+j38GR4q$|8@bYssNrvvW0zRuG+ko)xb%21B%d5RwmK{CPm(z*GZY@U^1ziPt~|F!"
    b")~60G%KVa?y*-sIRlXS_N~2qmB3Bf(2P?i*5ACz>yMysyNNT{Ort5JOJl1k!M=aK?vX$$eR5McZ+In9oA4pO!An(MGO_t;x2r@S%"
    b"B{{w{@b{R|EsMrb&ikQTM6n9pZtlwd3G`rUJ{kUOGcg~GMunkyV9*1DRx)V$GTlZ)Q{JV!ubC;gX84Y{yl9ul6LsF$k@fF?#`9oj"
    b"KD+yI%h0SP%TBPYSdL2=K8nk7FH|20vkz?Eoi>}S&%IeQw>>37uLuwRji|B{`NVkhU|v2++H5m5@6DdV#5@q^fjB!{n3N~MnN3EE"
    b"cIV~_LU=+r5YfPyc|u=he<w>0V&us|@;kvO5>XpjHl2>K>v?kyM(EQ@F5<{h-jh$2A?=X5NusuvP#X|iL8DbD?Tt#iq4~g}{a~^?"
    b"iw>q!YcOg)IoSZi{I<C`#wY-1CZr8ZaEvHQaj-R(G+O89<Hd<dk<nQ>8oyTtF;2^Ht_%mkJ_jgyD?8>2>+t}kXqShQ=aqG2z}kH-"
    b"GJ4-F2aZHw(_zR)2=XJ4s9JXmV9KoH=`~6rb3+)V1{6w(kBt=5H3?B*ge-%0hD+Em+5{bLrEi5*Lz0FaFu%Oxf#1hTm-7tu{M}I7"
    b"LC3!ks6G;%+@Qc^0Ft0S%9s#3vBE0Yvs^ds?KKXSACz^9n<sGq;EU7x87Rbrf_W3sE8_b&bffed(_50j2PxfP`3k$UHgFlzv74tY"
    b"ae=RS>Gfy+#aG~wcSW;Hzy@r&rF;@9u;G+HO377#UFCM4!W%q;nwxKr6@JcBP`Fvffa1gv87W*8$27XZzMMLxp$Z}o1@3J`zb%94"
    b"mSd}8yws7pB^3J2r{>Ww#u5cdE?HTEA`YQm6&b?vS|sk+O&`Kp(V1M7o(<>r#h_G5HcnqAV|zYv?C~e{*Wu*LbY#t~;urt4*m%}R"
    b"WEX92g4d9q$x{R)T}uUI9c@Cew?a3fE(zHLQNYD<1+^brj^hp|kPm2K&o7U|$dvSw>xB^rMG<^XusiAE))<8(TnS~W?Dxau#{NHy"
    b"Ffwww$jyzSF5)ART?fE3z3ktB8%)VEYk|y&LP81DiaPJoQ7AZt<I=oB=p|sCu^QM^pyIZW?^<e^V$Fas8*V)ujA|<vS9F;%38FH~"
    b"D^0=QLFOdoVL-<zS>t0^hOnDD*tbfSt_mv@kZsjABBs%j1af5o9jR&r=d?VFeO_a-;TJ8Yk%5AskoT_GklA7e!`?C)<}#vYh;Pk}"
    b"s&Cbn;9Fypz*c@purH$OlT8xikQpIy6cDc@12sX`y(-Vvfx^oRsH4%EBuZ|z%vn*LE33A8rnAiastt;hloGflpt2!FT_=;dsTK;?"
    b"9qx`+1V$;fZEibvnItg%X|Oe7OxGynIpR}7`87|4D(05+#U2kvBT#x5lV9&rTV6{Vt*??a3NfP|uxTjeIXKEf7i@e_p5wPQ{DWu3"
    b"!$~*3lO*o?WX-Xu5{sGVDrNQ>XH#i2W=x&yi5nDbaN;7+k0|_x{i1ech9Fn5uJG~yBJDdyE^vF;wRufe*Jaz3=@K)~5s_7%S%<ln"
    b"$(2+=izw>2lIEK<q!fRRg4ij$tfQODE4NQ2=Cb~`x)ogH_TQTd$vIDXSe33%rHH~aJ~fp`6;o-ag_84sfAprPtluaq{Y@!qf#0>%"
    b"q40cTZ|_`uM%BOP4=c%4`CXyG--SUcCU{Xd)Xj62QBA6kJndt7b|3BhQYq!!Ca;xV{z|EYopn=15j*cx4aLrP$u|;%Wlf_XxB?ey"
    b"Cwn?K?_d1&;{O3<3m+N"
)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _load_canonical_tables() -> Mapping[str, Any]:
    try:
        payload = zlib.decompress(base64.b85decode(_REGISTRY_SOURCE_B85))
    except (ValueError, zlib.error) as exc:
        raise RuntimeError("Embedded Federation registry source is invalid") from exc
    if hashlib.sha256(payload).hexdigest() != REGISTRY_SOURCE_SHA256:
        raise RuntimeError("Federation registry source digest mismatch")
    return _freeze(json.loads(payload))


_CANONICAL_SOURCE = _load_canonical_tables()
RESERVED_RANGES = _CANONICAL_SOURCE["reserved_ranges"]
CORE_COLLISION_PROOF = _CANONICAL_SOURCE["core_collision_proof"]
UNKNOWN_VALUE_POLICY = _CANONICAL_SOURCE["unknown_value_policy"]
SIGNER_AUTHORITY_MATRIX = _CANONICAL_SOURCE["signer_authority_matrix"]
ROOT_REPLACEMENT = _CANONICAL_SOURCE["root_replacement"]
PRIVACY_OPENING = _CANONICAL_SOURCE["privacy_opening"]
MESSAGE_REGISTRY_POLICY = _CANONICAL_SOURCE["message_registry_policy"]
MESSAGE_SEMANTICS = _CANONICAL_SOURCE["message_semantics"]
CONTEXTUAL_RULES = _CANONICAL_SOURCE["contextual_rules"]
LOCAL_WORKFLOW_STATES = _CANONICAL_SOURCE["local_workflow_states"]
OPERATOR_LIFECYCLE_SEMANTICS = _CANONICAL_SOURCE["operator_lifecycle_semantics"]


class ExtensionId(IntEnum):
    FEDERATION = 1


class CapabilityId(IntEnum):
    FEDERATION_OBJECTS = 1
    FEDERATION_AUTHORIZATION = 2
    TRANSPARENCY_PROOFS = 3
    STATIC_TRUST_COMPATIBILITY = 4
    FEDERATION_CONTEXT_BINDING = 5
    THRESHOLD_EVIDENCE = 6


class ObjectType(IntEnum):
    OperatorRegistryRecord = 1
    KeyAuthorizationRecord = 2
    NameOwnershipRecord = 3
    DelegationRecord = 4
    FederationTrustBundle = 5
    TransparencyCheckpoint = 6
    InclusionProof = 7
    ConsistencyProof = 8
    WitnessStatement = 9
    OperatorEndpointRecord = 10
    FederationAuthorityProof = 11
    FederationAuthorizationContext = 12
    TypedRevocationRecord = 13
    ConflictEvidence = 14
    OperatorLifecycleRecord = 15
    RecoveryTransitionRecord = 16
    ConflictResolutionRecord = 17
    AppealDecisionRecord = 18


class MessageType(IntEnum):
    FED_CAPABILITIES = 16_384
    FED_CAPABILITIES_ACK = 16_385
    OPERATOR_RECORD_QUERY = 16_386
    OPERATOR_RECORD_RESPONSE = 16_387
    ENDPOINT_RECORD_QUERY = 16_388
    ENDPOINT_RECORD_RESPONSE = 16_389
    OWNERSHIP_AUTHORITY_QUERY = 16_390
    OWNERSHIP_AUTHORITY_RESPONSE = 16_391
    AUTHORITY_PROOF_QUERY = 16_392
    AUTHORITY_PROOF_RESPONSE = 16_393
    TRUST_BUNDLE_REQUEST = 16_394
    TRUST_BUNDLE_RESPONSE = 16_395
    TRUST_BUNDLE_UPDATE = 16_396
    TRUST_BUNDLE_ACK = 16_397
    CHECKPOINT_QUERY = 16_398
    CHECKPOINT_RESPONSE = 16_399
    INCLUSION_PROOF_REQUEST = 16_400
    INCLUSION_PROOF_RESPONSE = 16_401
    CONSISTENCY_PROOF_REQUEST = 16_402
    CONSISTENCY_PROOF_RESPONSE = 16_403
    WITNESS_STATEMENT = 16_404
    AUTHORIZATION_REQUEST = 16_405
    AUTHORIZATION_RESPONSE = 16_406
    REVOCATION_PUSH = 16_407
    REVOCATION_ACK = 16_408
    REVOCATION_QUERY = 16_409
    REVOCATION_RESPONSE = 16_410
    CONFLICT_REPORT = 16_411
    CONFLICT_ACK = 16_412
    OPERATOR_STATUS_QUERY = 16_413
    OPERATOR_STATUS_RESPONSE = 16_414
    QUARANTINE_NOTICE = 16_415
    RECOVERY_NOTICE = 16_416
    REENTRY_EVIDENCE = 16_417
    OPERATOR_REGISTRATION_REQUEST = 16_418
    OPERATOR_REGISTRATION_RESPONSE = 16_419
    OPERATOR_RECORD_UPDATE = 16_420
    OPERATOR_RECORD_UPDATE_ACK = 16_421
    KEY_AUTHORIZATION_PUBLISH = 16_422
    KEY_AUTHORIZATION_ACK = 16_423
    KEY_AUTHORIZATION_UPDATE = 16_424
    KEY_AUTHORIZATION_UPDATE_ACK = 16_425
    NAME_OWNERSHIP_PUBLISH = 16_426
    NAME_OWNERSHIP_ACK = 16_427
    NAME_OWNERSHIP_UPDATE = 16_428
    NAME_OWNERSHIP_UPDATE_ACK = 16_429
    DELEGATION_PUBLISH = 16_430
    DELEGATION_ACK = 16_431
    DELEGATION_UPDATE = 16_432
    DELEGATION_UPDATE_ACK = 16_433
    ENDPOINT_RECORD_PUBLISH = 16_434
    ENDPOINT_RECORD_ACK = 16_435
    ENDPOINT_RECORD_UPDATE = 16_436
    ENDPOINT_RECORD_UPDATE_ACK = 16_437
    CONFLICT_RESOLUTION_PUBLISH = 16_438
    CONFLICT_RESOLUTION_ACK = 16_439
    APPEAL_REQUEST = 16_440
    APPEAL_RESPONSE = 16_441


class ReasonCode(IntEnum):
    NONE = 0
    ERR_RESOURCE_LIMIT = 1
    ERR_PARSE = 2
    ERR_NON_CANONICAL = 3
    ERR_UNSUPPORTED_CRITICAL = 4
    ERR_CRYPTO_PROFILE = 5
    ERR_SIGNATURE_INVALID = 6
    ERR_IDENTITY = 7
    ERR_KEY_PURPOSE = 8
    ERR_KEY_LIFECYCLE = 9
    ERR_SCHEMA = 10
    ERR_VERSION = 11
    ERR_AUTHORITY = 12
    ERR_SCOPE = 13
    ERR_POLICY_EXPANSION = 14
    ERR_ROLLBACK = 15
    ERR_REPLAY = 16
    ERR_EQUIVOCATION = 17
    ERR_CONTINUITY = 18
    ERR_REVOKED = 19
    ERR_TERMINAL_STATE = 20
    ERR_TRANSPARENCY = 21
    ERR_CHECKPOINT = 22
    ERR_SPLIT_VIEW = 23
    ERR_WITNESS_THRESHOLD = 24
    ERR_FRESHNESS = 25
    ERR_EVIDENCE_MISSING = 26
    ERR_OUTAGE_POLICY = 27
    ERR_DOWNGRADE = 28
    ERR_LOCAL_POLICY = 29
    ERR_RECOVERY_INVALID = 30
    ERR_INTERNAL = 31


class KeyPurpose(IntEnum):
    IDENTITY_ROOT = 1
    RECOVERY = 2
    REGISTRY_SIGNING = 3
    KEY_AUTHORIZATION = 4
    NAME_OWNERSHIP = 5
    DELEGATION = 6
    TRUST_BUNDLE = 7
    TRANSPARENCY_LOG = 8
    WITNESS = 9
    ENDPOINT_DISCOVERY = 10
    FEDERATION_AUTHORIZATION = 11
    REVOCATION = 12
    GOVERNANCE = 13
    FEDERATION_TRANSPORT = 14
    ACP_RESULT_SIGNING = 15
    ENROLLMENT_RESULT_SIGNING = 16


class KeyLifecycle(IntEnum):
    NEXT = 1
    ACTIVE = 2
    RETIRING = 3
    RETIRED = 4
    REVOKED = 5


class OperatorLifecycle(IntEnum):
    APPLIED = 1
    VERIFICATION_PENDING = 2
    VERIFIED = 3
    PROVISIONAL = 4
    ACTIVE = 5
    SUSPENDED = 6
    QUARANTINED = 7
    RECOVERY = 8
    RETIRED = 9
    TERMINALLY_REVOKED = 10
    REJECTED = 11


class RecoveryStage(IntEnum):
    RECOVERY_PENDING = 1
    RECOVERY_VERIFIED = 2
    REENTRY_RESTRICTED = 3


class ResultType(IntEnum):
    VALIDATION = 1
    PUBLICATION = 2
    QUERY = 3
    AUTHORIZATION = 4
    LIFECYCLE = 5
    RECOVERY = 6
    CONFLICT = 7
    APPEAL = 8


class DecisionOutcome(IntEnum):
    ACCEPT = 1
    REJECT = 2
    PENDING = 3
    RESTRICTED = 4
    QUARANTINE = 5


class EnforcementMode(IntEnum):
    NONE = 0
    DENY_NEW_USE = 1
    REAUTHENTICATE = 2
    DRAIN = 3
    TERMINATE_ACTIVE_USE = 4


class AuthorityClass(IntEnum):
    OPERATOR_IDENTITY_ROOT = 1
    OPERATOR_RECOVERY = 2
    DEVELOPMENT_REGISTRAR = 3
    FEDERATION_AUTHORITY = 4
    TRANSPARENCY_LOG = 5
    WITNESS = 6
    NAME_OWNER = 7
    DELEGATE = 8
    SOURCE_OPERATOR = 9
    DESTINATION_OPERATOR = 10
    CONFLICT_RESOLUTION = 11
    APPEAL = 12
    OPERATOR_ENDPOINT = 13
    TARGET_CONTROLLER = 14


REGISTRY_TYPES: tuple[type[IntEnum], ...] = (
    ExtensionId,
    CapabilityId,
    ObjectType,
    MessageType,
    ReasonCode,
    KeyPurpose,
    KeyLifecycle,
    OperatorLifecycle,
    RecoveryStage,
    ResultType,
    DecisionOutcome,
    EnforcementMode,
    AuthorityClass,
)
