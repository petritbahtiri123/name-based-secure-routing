from __future__ import annotations

import base64
import hashlib
import json
import zlib
from collections.abc import Mapping
from enum import IntEnum
from types import MappingProxyType
from typing import Any


REGISTRY_SOURCE_SHA256 = "ed48559f233e8e78e90cf99c178f08a4e5f5b3892e37b3dc0d191ebd8b89e70c"
_REGISTRY_SOURCE_B85 = (
    b"c%1EBU31$wvVG65VEOfi<HU9{$!y&RMP?H2D3XSfob{dBV!<RNV?&V~kg}uMn*V;Q0T2W!e#tgyJEOcLp-"
    b"6l*4o){3jmCdp7{<{uqHC18H<%_Q3Xgs<UcZFLF^!faz(>CrN8wdM%_a6RMJb6w)5kaF&FdrfT9Tr4lfYXjj%jp*efSv%QM|@sYG"
    b"$RdcW(*B?vi5sCltFxL4w(H6a<mSigx2DAl?>=8w7z7kR-"
    b"*vaf5;lP7Fk`kyT=x=am>!UWt*Hll)|iqYxV;F^~~sx<(<q_)+%3fVL<f7@II9fsuIEc#RSRg}!lvy)>e{T8eK7zQz7eydxB^NRm"
    b">5q2vF3VHk#Sgukaa1PQvthsVFO$A<Wsy%M4|ljle4+;RqUdopIliC<YSGx3XO9i=Ni_>2AhZ~py}hhlU^0+Md`X^}hm@K0+vpFM"
    b"EPUUsT`u$X_IIQIY5%H~8%3+B#XJev+2YdpMkr_N;Zv9kN8S}LE-2XlMq&Yi_<?hYqkrh~ct!5-"
    b"Q3%c?e<=^ldNWIVV2HFrPQ<8yobsj3Zc^bEph$C`bfjLu!_!aldgL#wLpw+}QqqO1R4FLl#xj9aG0BnHZesKe*{*1=vx{r;xMuXs"
    b"Dyq}LH8e=?@3uV2sP7^5|w+=iGY*Cej5T+ie<#{piobX(Jukg8%%H%a<o6Z%4p^)nkN3X>R79D3W~HTJ&65ed@=o)Hc8+o2b1K$}"
    b"fz6fLXj{aH)B!zfHZ>4)C7w&r(QYW_;n5GTnjMJa}Ft7?9)rRI!btk7qp+`ureG-"
    b"F*bO<FJf*RT6&0w=p+6sGul<ygGdWD9I#>^t~I*o6&ap@;E?QMe3<ms&T($DvnAIj_&O;&4Qk*xPymZs@!o)`JRfFx@itBQ5fOt5"
    b"yCEPNHDb(gZymIEZ76f^+PVq`CTc4`d9jagv}F?qUsnw9eh(U^-wHs%=#-"
    b"6W*S_(`Kg@YIg_2U+Y?+2ceTG7|IjJb*$mUId^|sSk7f#6W;dH1jm|9C*zq_*9tu#wZ`Yui9Mco62!Y+n$RW)P1^hG*m7o{?P<1p"
    b"onJNz<Nd4Nn$aSV_j*)$UO!t(Hw)vWmnO6cLXRrvOZpFs@%hMd9qYG+HJjJ9;H-"
    b"}pGz;O4{w6G@=Yx4|1K#RyK)t?ruW3E=*&6=JS*md!ywhEK+vw{dM|(UREoR_X$|hpNEI51hs;5RYiQ?>)9$Fku#xr|1&wY$-"
    b"!Z_)z8O`F*LylkV`PiDxTyTF{U#xMh81yh>!PDF}5^s8GLh~r-"
    b"AxFo$m<)LXri<C<y2^jnU3o1ppS^mgyY2>FK6~|EckM0XuF2ywoQyw?>>;Ry>BOl6z9wIfth|2IH92?W(g|2+F>4%pP5zy76WYdK"
    b"5B>eN7&wFR+#Xx*crv$#wbg6#^H{^lh2>nfRIZEjtnu8rY}{so+JDx)djDk4=1vy{bRS309h%Y%$oIWCHJVlmXD6?EY(oP}ooL$e"
    b"vo4D};qG+tVPw~;=aZA3n$aMM)1I2pjEl2gThSyBJ-j&{e6ifz)6)Wrw|%ssK?XnfQGYWa-"
    b"u2gnCQ0bw%yVmGed<CGr>}I^U*GrB*ShO&M8N4uKh-x$;ItR-cMAm0dTB(16yEgGfMzhf?Xe9_viMo|qHZ=BExHiHyWSeoAPqh2I"
    b"G9eY!KlTuK6|CN?nYDk?4cq(DMm>Yx?beBZQqV3<I2|P5rgG`Ej^nooT258>@RlpFleiLI&i9mf1<6*F@#VK#*?u<9E|#llY^=k<"
    b"Jn>g-W=E@ckFpx3p8m0$8m?w<#av)xAI4OR4I5(O2Bd4nf+-zm@gd5wZ|8Ok$v7@tQ=Giu7r6_%&w*lc*k*JWinkj(@8bV-"
    b")XIQWPh}Vm&59Tey?w!ho7x4gC3*fpwbJ=feoY{1LB}oxsBap{2LeXWLmAX^s(1;GO~x4uJy0!U|cI|ebnVlMxzgPHi|yha;)iSP"
    b"~(BtR;l&d!p`;|dJJo08e#%Y=S3Z)^$`~Axcq8WDg{j*O{jHlIbZDYV8nMhD=iUyoTZ*>sjONbapiFbl@)7buIb30yBD_gwX$M;^"
    b"p$OA%Tp|s_3PuWk5DbNpt4?l1eR^0xL@qqtmeFsCPySxKUvHNpDdv~D(lwAW#^Nx<4?}uyn0^iqq5OtI2bi`Ss$OteY*x5Ta&Yq8"
    b"QJ5x<&10ARS&h8{)V@1yrFTFv@NDHo8NUNlO9*L*&y_{uoe4*mu!($Gs%0}0P1f+TXgdGx0uac%l)lj)fmbCR<MO*x1-"
    b"6Y9?yDlZQbL-HFFW4+q3%FtLu2z9tW&7t!DFpryiHGpFq&#L0yQ)scvC&eAk6nX^LwcPQm567|ol=`aUb#9c3A0$Hm%w&(^<s)RK"
    b"eY+`j11`RiD7+v!y|vKp(Gw0f}Bu!eppJVoLNVrNhdrqhvKv#!@7gbT~DKiXN$tW}#N;Y4HY)&13jvZ*t<u)!hM=Vn6v<ke$y%@#"
    b"8l%4)g3)f|CYS*fmw>w4qkUEd_7$I{ANZllXapPwE}%dsGLPEC~$x7*7PNxMmkR&D$!SL_W`rFWU?HgVR8)(Bt6n#~=%Za_{SY&?"
    b"=p&?%J+^O@+#`_#nW5CBqddg~d0+PHc>I_i-;1dSV@dIRVC(^FY2Pk%~^2hTjPiYm-lU!+!WqfP2X>sA|cIJBm{I`}|~^fy}@RD-"
    b"USOA{~aKJlV+{er_~L_L;2$X!3RaIAA{eCdv@ukNBIBu&#`13iPMd|0;!s;9Tkz^+sVr#kIU7WWB@mpUPzJrL4RmZ{100+h7wRmi"
    b"g~kF;q~I9t>2?!~!vVT~qJIAbhNIywCTW7qrIXJ*GPKK3_#``C3KOzF>75t}tVM&F5O+H5}cx3E69W^*7omLs;IcKs)ovzYQ8_b="
    b"*gQr#z&vz?<Jw=m`d=aU7wXvcF1i>sbbukWqMUWit}0vgjB?7I|&+@aBuQaStEP&LNMn>XU$|L&FsIWOhs_EKu{#pY$GQDk+6)a6"
    b"-IN_l&Bru6Cc+qb9hD~qZL`OiyI4?fkkrzX@vZBDmBD!ui2F&#>2cKj<X>d>uv2U%XuS(joe{W^IW9Y(xqrMZ`Unidv$L2ud%YO)"
    b"&@F*lVYC$1M!?0QiU@IJ;YXQ-ULKqpCzJnYg9&m*s-U(YkBv;68FqLg6Yh{9lNkT4-"
    b"WHstI#>~rHaOUWMM8%zxnrkKVQLuz=G7{iESLrkrg2A`-ejffhU(uj)W@jP)mjH+mhEZu|@@PWx+GZDomtHp%QiKp4OtiKhx-"
    b"+8wDH1eV#OQWy;Xn^)|EcccBx@2FA$0uO>mWg?XEtKNcBqZz2x>VX4eb1i$yi*zzhUANV%6h+3R*4Lc*a+~4d^i&vU=N1pYHN5wl"
    b"we<E)<5=mLf4l@7^Ma>!p#~};)#zlRBXAX_)8UgCJiwnIcR08B{N8^C?~l@vz%#?@}-"
    b"p~XLD}A<i<o!JGsuyHDEqla>5itkWIV%_5|4zrtQ>@sA)6V@vtJ5kmNrs2lOvSN;g<e!cF)sjBZ0NnEd_(F$o3l?6{SL0_kveh$("
    b"mMde_igU%j^h*d&evf)h85l#WzzjD$`}8_VarM42OZhx+oL3I>9FTvADe=ThI*%(H5c=T9s2l>D)vl$EDNb)@{DD3}tpCS(<2>gJ"
    b"MMqm+{G`M}nsrB^6P6p`Rmoi3`yrw&z@l``-g7hg+MpkW-"
    b"P*Ayq$QQ#NqX3$pOGYpP$RlyX<rm4NVOUz;mD}S$Vm||MMpVR7wWx6njbhN%AA)DLG0uBNbWNuRY$A(bs7s;$9o&UYYt<||x6idT"
    b"feT-U@E2xaHsuy$*U=(5)Kr=xpNtU4J3j<hnAHuyxuhMT(6hv(-"
    b">H`efJ@LGALxXNvRK~~l1l<aEPd|;@8?)vuNw3Ysi(*_Huj+d(?lovF9?qhKYC?@0Wu&+{;Ln@Cm&T~M3glix*5DQ{4_DKRkIX%#"
    b"OG^F@67eJeOz0y@Hx!$qBY)xqTy4>^D5ae%RsODWN^(I}$!X^Tn0v|TftjY4`BZZe&BNHH6^`tpL>kXXJQW46yOBB+ed$u4dkts("
    b"_ES+#9nPHeHl&UFR*%u_wn3&*fXyVv9$6BvWmJpzBpt@~v73EgW3Tf1DP>qukYWnO-"
    b"4wi_B`IZFc`2eRoSNWurBM)ITI_5cM#|;wO1^22a98w|$G=(yULo|d;ETdn2cR$rVj#jKrHF(Tojpp>8k<5|3Ym6AWhU<s?$Qm+y"
    b"iX4#?$#yN!%4if*eWl$it^Y?;@!oF*O;!rU^RUlZcW$~dWMob(I&|vcB^H?ob6#4r6%%yGomK`9;47VQ&{$w-"
    b"xS+D=IN_fW`eya^o7@JZ+^qyk(UP09&9RHm3zJU-VlFV-"
    b"G+*M>@EprvOJ=a0aX`x<QJ~PW1o=3Wnl2dzKHVs4GM@4dlw)ZH`|kP)mH6%lkKLky5y$GaqS+-"
    b"3so%2imP~sUoUF8^0@0$RK&U(y0`6Iz4|F%fB3^}soc{vslA->Vb+I_v>Wj9nGNEP>gBAxck^E8YK|JbFD)rSL{G~v-"
    b"OXWs&k?J<ru1H;wG(A|7@#{1P##$sMX5`193UP)p~Qt`aST~>g3`o1kfs#NCL=ntASm^#JXWUg6$yPD<Isn%Zn=lGuyC!Z3<Uv0j"
    b"w`#Snra}3m_}=oVBd|Xn_{{qAqrg9;WgSao3IqCvL;DF!j%h)VG?e{zy>75XobxyiqSU`uFOmz+@hAEj48Q6-"
    b"qwv`9FlOAOR^*1Gy=I2DS7l#K{7&!Zq+BJ)t_7uu;-Nk9WPq1Ny-pWj(73N3M=b_BalB%QkVFJh!zqP7*Po$^=JG&CKM+wN{<T70"
    b"O<$V-"
    b"7q02gSkW`*ih`&#wukm6l0dk%eN!6@kv?+j2u88FEORqce79<CD8cm^qtA`%9@Zb98RpmY&KuLE)bfGa=r>855SW5nLR1;+|e8*-"
    b";5J=#loJP?mRi$dGcoG$=jnHHpqJF`Zyprn4&8l+Q>)JyxN)~tZs!voRH*r6T@=I$i4#@89c6tMOOwS#S{f1RL{7<UK&v)UMWS%x"
    b"7Tv&!xCu|z%U0vbi1?u%J2liP#(-tu^Nl0@&TKk1*HNbF`hVI25^ST<V&C0Vc?;Kg@7tyJIIx&$?<H)Bn+`{UXvt^D1m^_B-"
    b"&69n{1;9`z8sMB`W*LU89gJVKV$;9Ql!#9A`nE$9W9s@ooIhi~|$`DTp$YpZ)_d%~^XxDNGg_;|84g-"
    b"31N{aEe|2RgtaWvjC$I7;P=ya7h?%(mHu7uM;R3X17>D7v(L#D80rYjD7ctE4<n%VS*PSKq;msAi`Xs6z`w}EmKV0>&+U4E<Y21f"
    b"_z4*I!cB^X1FScFhcW%FW?F#gpGWH*C<ShmuWueg$&c>ZamkEHcaD%n;?)Xj1o9#kp1*VM1SV7%20S7t7(>^gpYPwoi#)ulbtKl7"
    b"3?n2ngmR~c_5^TRupsfEQNS`%?%>|2Gf)zI57Y%C?!_`Hk2@G*}h{w-"
    b"Hydki{rfb<Ev;B`XUV4VB=z>*Gh~oC@>6tK=3~n%PXREe^R|Rp^s^a;0j-"
    b"wir8X|X%%027<lS_rLd4vMsv%h;?F)}X3myrcfJ!+DmcLj8^{!vuO20_B5oeyy58`aP{M#RQtZ8=tL=#RcpXP<dz~Q@9Lc;b%<Yc"
    b"9r)<J_D2zfzJc5zLix2{u7bd2vE5pfIjSMd=9R0-"
    b"1hK)(bEOfClcC|183bDC(xx^k5R2YTj&BGFg+4UWF$1yDK2wf)(c#M~8@GPB!Od(OsL&`T{vWeq}0zN%Tpu2$~XWr9BDe}G@FscQ"
    b"k<?H%*(veD#W@f7ClSC|c$`Ez9otqd@m_ami2pU<8wZRv;25h-Uo7BMU_yQY&HV_JHBWs9i-"
    b"uXC5#iB0%y(=s;t!cs$I^y95B>u4}^t%m<Z0r({O6Xw*525n}IGT{j2CHxMRZRy7kYKb_3%t5O`g?*=Uj1`-"
    b"Jf<5Os*DK>Q|iOPCb1SZ6STwzx=LV#3>ML3EF-SnxzcAt-UiKf2-RTk-"
    b"k6rqq&SJAFv0zx^9ED0Bp49qT|W|4_6$~Y6Q(2(>p@d2#XuYd5SK49YhY9?Ld5RKs9A(r#;DvZ&5&ZiwpmKjZEg=7`1QH-YbmI3P"
    b"kt>!vzcEzp_B7#_Nw8b&}ZAliQ&<0oJK2(;%kssuoZNgMvPm9OAL;yioP8v_Q#{xeev3jVwH<?Gxuc^&C1G5ioxFmUX)s%m3kkLn"
    b"VnE#3n^b7(lNYiL_%gJ04)nV8Z6}Lz_HJjV=K<2{m;(9tbHxo3Zyo(Za1)U+C@21sgJ3O*yA0vX6vmLg%y9eGGt9~z+8C04|eVkM"
    b"8XdPXhF#gM74~ZqkHO1CLg=8F+V=iXz?-!mzS#EEg6V!ut<Ey!eSyASA@CLQP9=-"
    b"s*8>9>gYO9b0v~%k74Xd$7PsyrQ$lI=H7+eoXsH1T?x|WC21noZ`oG9M{rMW*8}%HBg6{6W$>xxTlE02yq&ue#4J+TykaMm&14&T"
    b"^@NMK1?wC9Z9`<?0cRO9LVSy<y5S&xecBrb2R>~<r+R*UPckiGu!%{#fUt^71rTBNl?NOdSVV+BZRqt&mD2H&N%?t_<z8?UOes3t"
    b"i7FS<b2ylKN03f8$u(^MXJnYkJi{q0u~eV}Zc`=kz%xNEk8nER_6gy(HgcdHv;z+g;{@1W;Y2R;88o>$8q>&w9rJKyh}gk=Yxa)~"
    b"Vy*)D8ACWbp9d#@4CHw@PSKM`^j`4;_klCYh0T(-2GQzAM|6e_)@&Xwm_tgmScU;BM-"
    b"}Al)=ka=l|5Un*F0T?fl_9*vJJ7!IgnC}jfDK!6IKgN52Dq<O5GQXH933sG*cCzwHc}HSSyDU@Kcj2^0L^0PEiBx82LerQYDkjbE"
    b"3n$B2fBFWv}bBygeR{7H~75^hh<X<vX(>$+9{b(Nc*W5V7oBh>Rt{$ts)q<d{(`1rOX<MrJ8%*PfiXi@Jv+#%xQf7)n)uA6w6N2H"
    b"oF=B)QA)Iq~DZDD33h98ShFdp2h&&mNW(y*!DVafQ=cj6);6jj~|sT#18~nDFT7C`x<s(jRE?{(#&`)3>j&Sb;rV)aXTF2yuDgs="
    b"R|Ff!K<?12_IaQ0&Bx;*7LAn-As|BvZI6FsGZVfCzu4I1X#DK7-"
    b">z#y0IxBamW5S11%o)7lU!iq;NH+4R1VDLVM9u(^|^vnw{`dFi%D5S|sTS#!&14VhAumshL5mCb6S@QLvBD97XtzUOV^%`~o2Vk8"
    b"^S!`R3EzJVcK;k);KdXI`6L<2s#g6N(VZXY-fM1r(Q#dk+(uIN>uW(Ssw;m-nJS#~WrrpJ&VeeXQs1Q-"
    b"W9NN&UKy&{)df&WORK+Q1hVD6a#xR`mg5ymi4O-"
    b"6L4LUh>?eCU)q@OAv0XX10Gi`nOD%;%Zo>i0mQO90#KO=dEX^&0yGwnP=;1(QLXLAk+(audzd-"
    b"ZY9g$#vhxL@v%}#mm(RSGyV&N~b%ZwstGD0knlZ(A*uxw=Y@vv^XYRL^PM-OM|COd8tD8B}X;L&EVpF+F(BHfa-"
    b"&C_f1a)#toaE4M6^FgV}X|A{&YdR*pp$4IK)6^Bf)wsgS*<+ac>iz}}C6%3Z5hL0_}U+W^4K%FO_{V+C*+)}60@9sy8~<>WeO|Jo"
    b"gaEFm1E4z9_eB643=Ko+u|BnHJPBCuNz*^VS$BWfgZKvMID;9H4LxeVKc>XDKgBJ!$aUFrwNS=Y=wH&?a_O1F(ThMxC?;;fCC2%i"
    b";%calxFqxT9<=rQ?LW3@inPaRMTRw{!+%#}CS<`SD?_dbItI2gdM!wlQ3@HSxX38{lM`kZi?h2+&_SAngA#jI1RA9+D*ttBcp2!u"
    b"HxlTXMG70XkkqvE*)z))EAWCtA1MnBYf{&HIPJuT2O1Un}9sYhXLL|%?Rk@1J0;O~C&?#>6DpPSJsCH1U`@y>u0R%hPpI-"
    b"~Qq#lRVi=l0lg$CJ4|ygNw8Q3}Tx69Wb;fq=X}Hi)0X&sRi(9C=b%)zc*Pyhky5goFEc#d8>?P)$!%3Uxi6cHafT|K{*H*8t*LC7"
    b"<2z@bH*L%6TWL#8Y{Vg@h>rH$Mlecuk~7?X+Mzz_eeOW_bCB%-"
    b"GKCGWpz{TH|wj{0Z(plFu$I$Np$H0K4{<lY1fC8pDMk)&*R>eh+BRHgOyPv>`0!nnqb9%S$E91$_RQi{PcPjzR(%ufr90`%{d3!U"
    b"AR_dxPJVNe+HBahSF<a__cn*4X~tT1*~~>>1b#{2XeIHJdy3aIOdG;*5YuV9qjt*Jr%SGh_0bbK0Y8WPf7_^zvFlYeaT?L%@lz*C"
    b"1Mv%15xVz|yud<acIt*$xEL&O>3U1KYg@(&W$<iOT*)*)LUq><!mWtG#BtiiCqAnX3ZU{46SvH*}eCH|#|4xTlW$w0E{Zx&Zx=R("
    b"rBf&nsHyE>O+(^wkvJb=YJ{Fq={Wbi(A6;skC^Fc26DQ3{gE+z`?qCcF^h@{n?(fUetOI<o>k&Z+;uAAxc?ccD%Np7py4ogi8h|0"
    b"2;TV3{2Y41F~#Ku@%J*e-Y+Xm*cY`PI5CUi$4$7avA;T@c|nylv)9<p4rvev13OOdc!y4R4Ea-kohtIJN~#R(Ua-"
    b"2Et^0>pw*B88YUtcv}c}eb{WkyRfV!%Qi^X@MMP09XuXr@>$a4UGR7xnrt#L_hHH0yxc`1jrjP$f+yen;)?xA(dNO<e4?z`W@+A$"
    b"JOQc)`|?1X?Zi1Ae6id-V|t@;DHEM{B+pER!ySc6UjKrJbIbT|pWP}b&19t=49q8%>HML1vINTdb$BO07C2HY!X+4$4^@6-"
    b"!qG;LO%Og1q;??QnH?M5mV1(;YFR4W$dz_P4S%B?yTl@==@Qe&rN@II`Q+HK)meFelFU(=q42<!2d*q}<+(MoK6P+W=9lE`?Wts`"
    b"^34!Y8r_N%xuU2&Sn;KLXrF!G9gGJ<QUfM6U5}&Sv6dS<VzFkGtz7q{nvt5<*84*FK$3a^c_)T!vLx?7khv)-"
    b"$?>IuzsH1bSu}=n-Vfa(idE=#b656Hpa)a)$?#{JiTPkODh$m7gB}>Pl0nOt={6dg@-E$d%}lv9!*|5xMY}wnsPo2-"
    b"tbhMAo(DVg+1-y@hGs2Uc7kQaa$LgjQCyaLq543WePHwMwAo~R?#-"
    b"IH?I{s@MR@RUM3tS$C&rrx^YTg3W}B&bZ}t=>=7Bg5#M$A(q&x}EY%*H3J2zJl!V|)Qhz8Eg6Z$IqJ6UoNBTo*J-"
    b"w8&Mh}y`q>2!=;&zo~FLZ4Q05l4>lo_wkdX@}HJ61BC2+JM*!8m&TUZ&cb1%?A$c2b0}dbTFM-gHiLz$p#qax6Q>dMgcf8A#GTKV"
    b"?<GkgRQZo(K<gLFHTH~jLyo@_`NcSaax9RWjF}-"
    b"IY7x<*)dmGj|V74yF8RUudE{j*6wqW(fe*Wa3lho4nsCVkRO3W)w){%Q)V4cuTct_8^S0xpioMDY^0d3Nr(a?WEr$GT*8LYCg^Z0"
    b"eJiXQk~Hjq`Q;rC{60>)oM))#?}pkAI{t+~^^xf01_dqykOcKn#)Qy`6;{EX<+^ciuW_jSpsZ8eJc$DUU!2y@Kp`d+%$tZ_5#Pt5"
    b"8>QEn-jW19Na+U4SJ<7kfy<DN-8^lH3w+H>uRrrIz5<WDE1F#bHekyw<&#i>4X6B3O0ELzD!2O--ryP3+<bei@N=Gm!p$-"
    b"U6eo_zNa3P5rqK=d<<uz+RS<b7aBm~}Z5c$j99tFRrH<4sq0nzWHIIHVmMBPa$;uKGaR~LQ$Pkv-"
    b"B5}uV`Vh{F&g7!>Y&f?s2BlK6ar!bD+w+NIk3Xru4kurxBWrFIzxb!c#<NBuyJ&M0yoU5lo+23OS}GvxXcL0H6}l01NysLM0xpg#"
    b"sQuV-9CtW@d_W6(et8^5rlgl#FN{Dair{mC-ANa>#waA=N+?rhzaJ(y_Wxmok&)9yZf+EH5g&={Isl&OW&Z};U`m!*3uHzV5=x*}"
    b")OnYVLcu8<m*y2hF9GX})xf3#6}N?a*HX(AYX*ebaO>e<R9m^YqRWg)5S3Y8X$t-"
    b"hGAAhy13FI08Xv<lgx%D^zE!exRal{bY^$~rF^!fakSh!5NL3>^r{!7f^BR*4zi2Uy3={-"
    b"~ym!Th%oZ~k_Lk8wmk~8Xd~0r0eXF(v-"
    b"x`|)w(>)QeGyfkY?2s<%m|62fOsVts0p&}Re81!6kc9H9gWr`QF5zg&Wh?>S+&(Oon_`%ZBU$~l)x<kl?^HCI+@H(wNSY3aCfvKF"
    b"iNRybKAMgB!THqgRK!`x<(<-"
    b"5uXyuuX!p|F}IvA_INNFfzrE}{Cbz#@><epeU+q9h#B>OO+zWq!BG~vVB>r89KWsMA3Q4_PP*}(Byra#YmQBoSj;?EDYMr&n@XE8"
    b"W9nQ_+@N5C6BmJgMBz8=7qufZ1i6ZJg^&LiY2Pt&f!o8b&1<r{F59L|mza5uh^+F=I?T09uA~ZDL{Z0;G~c8lrTA+U#7@~|9o<}B"
    b"xqT`zm-WBZt>7ZJ|K3zc&Uwnis&suSMHHU#si{1wm`Xb>l$`(jqc=rm{YFvgZ%R=M{H~=Ah36Z4d*|Xas{TEHSV^wR?+Ok6E(}sJ"
    b"!Hc?~Zl1G@YEpgVX&=k8`)KEvN-5_yd9C#FS4t)9teYx|*m<XFD0aR}zL6L#YZ?W?6}V74+0(gs|KhI~{|`XV{I&"
     b"*XvVNamq2<?Ojqkb4Ugv>eC1HmE130sDvSw+?Alupzf-Q+S%wF@~PgUO~)RMroY$v?rBBZ`lfBjW;b#?WBf3d8Cn|VC*"
    b"Qumu5C&4^A_{};w#K((xeiMW~{Qn@jPGbAUpZc+v!YlUF|7L$XIUuhksh2Jje9K$FC*S-j{_KbI#mtXVo0me~y$@pFy@`GQFD&-P"
    b"3lpC__rh>KAw|23c^FJqSX?U%tuRPZe`<a6!lj>BUhG@E66;b{Vhv~|mMkav)#}Y7-wNO>YvDr&BYg3#=!1oAQ9iJiQ5u9+GP(0-"
    b"9()u*t^OpP$F$nm{}%Z7{`6Pck=Vb5mc@aO9se&pfoJ~r)Q?btZZO5iU&v#N{Y+koycv<_Tj$alw#J=)j}*s#CB5Y0XU}R%mwoUz"
    b"`TI}${lUarc-KJ~q^nI@<o4hE(`k=KJ8s!wt-4!R<M;hx=l`^_IW^LP@vzk!4O&B|*Z%AdhW-BA!tS3LseCks-nQNG@M<)6+x?FN"
    b"`0txew=@1+)P{4@L(uN`#?HUS?wd~UveSE4)P@T)gYbUnjNbRVm#*`va|uJ?6xID=N0VcI{co7wZn|3d6;q?XK+2fMLptYILw_=l"
    b"r_D`|5B{pPOz-A#@E2h!ef?%8M-Tq)-$$Sw?t+EBax;_T(hvRHif$X45<*ps<7JY*Sw>T)#+sQ8u@@x^P(9IP)xPs5Ul;QrN_RXX"
    b"O6u=KlW>XJ40P-Krl{VRM(S;Y?nb2#-PYFp%1F(B1Zm_a$p{Mc@!O)BUmK~JGmH~W$tagF%&}ptGp0%P!aq4_rU{hn01hb_R)q~Q"
    b"WD9^sm=67K%q}b$i!)Ob;08?K)cF=nVHOlp&dIq^9Cm{nf3li{eo5!eupU+j>yQ;;zo0_?FO156=qK}VS<wVD9N1bcd@sE8CqYtP"
    b"{i_`rLo?t#@7Awl4S}WTwp)W1u~0is@iO7X*(+mqYNmF#)&8Jsff<DM2WTkwhwjj6_lKA6?^n+7v#tp*8fgNU&4Ye#<mg&q2Bc2!"
    b"a?tPe#<c|Ts*xsC3Br)}{-fs%NAEiWzIq*hE)~Y><Hnj%A&}Q*RJp95ETzkZaoR`|sswRn$gO}&`Zrg-%dP`W06C1tx)z)_(SmXz"
    b"T$pdd)!?!<);8dU`3C6q#cM<BnfFfn17)ewdGN|~?Ny_1h8#P+cK2$8ekDE;OJ>3O@o__qC=<o`u^Czf$J(ef8cQEzl`u{lYeu;^"
    b"%#h<BopH|@ja+npIv<^$Rt)DRH3aoESB=C)BTXnD1vBJ0bUyXlv;l*w(R*FxFHKjj<>m9^SElPO;pOw=*QRT)7<WS+A7FvE-A)_T"
    b"!k|CY0srL0Y~}h<H{{$AODANVt5NCD8}jeun@~0WX6Wzts}}5ejXOQZ?e$^%Nn5=kKMyR}K7r^fDmTS>plzV;vTY`;{iW&E`#aFX"
    b"!#WD+<W-|hDF@{1Mw}XDD~0pZ;|AMM!cwP(cKn>r*`09E&2PFLt$IE^ZKxR~k~nLq3FWvrZ?qL<@-V}jz1By^m7bmoSiESW4J9&o"
    b"*+l*2fOyqh6UroEhBGgnuJf)AL7W|%u3z8xvlG*Gmm=Wow3+J5ByiS<_qzfD=Z!R?L<$#;G@u*|FB)t^nJiwKUet~H-K#pp@T#$f"
    b"lt{x2JGKS`r`4^ntj~|l)?I2!pYJNtGxog%;!Y>?Y1Q^^uiq<djTtdG!y$pd)v)cj-Ok6(xVf-7tQ$f)i-mt`tjZpSP`2RDPP^4@"
    b"E=~@szUqyx2I$SfO>)@$(zW2+SPR<2&x3Iv-O6t}U8lKVIjnosdDjDn%FuB;y-%%f=d!t2IjkOC31dyn?n`5};>u)jH5~MdVgAZ!"
    b"#of+Zr~SEIJkYPr4K!?OeQY%t9fy^IvudOZ*Eh#sVjH``_%|wIaD_A&^G3M34;BMB<^DB*SbUwR%~98|-|fE9*(etVwd0`M`rKf6"
    b"8&(PyQHSq8G#J)KG(;br&R04}zcMK3PyG*0p;9<8$5mrz__5OiOOWhx7Fr_aI7>a%QdqS);*xO(g%ulQt^ouFx}Q4EAB7d0qc6Ul"
    b"El#l%)^Co#-eR@bg2H;u5g6Y@aX)rOBh7iCQ*%_-zZ$pRIZSyJ)@_c<F2Mu%ZrHjkp4aB6tP9lLE$i}YgDlGS?MiIyGjogveBumy"
    b"nswE#7Smt-mAhERi+NJDnC3P=7!UmhSGIf*np@bi{lU*<k)@gB4Q&85x1h~B`I}qJO4o98D_Au~vbhy(=Gbkw|E|HaUQ}B*xNzkz"
    b";>*rRKYL9b@7myi^~s6hfTsqRvhPsPy_PP-<IJ?MDZX{#Rp&d@S0O*KRptJLlikfJs#bg4`Q$XIrpBFNqw0y&SiGt{H#Uzn%h-!u"
    b"os4Iv0BeH^Haof<&C=S45MWk!-gbD{s-w+QaB8sj;{KXJ8Tivbb<ii)q(5IjdCizTqpJ}PrPH9_UIsy4HfQvdS?{l!CMh$<4)=O>"
    b"KbN}Qjt%t|)7NOK+}(yNJ*VtKA-7fhC>G5nRAqLh=$3KTsnH-?a7&Gc9o>MO?QA@fWmqel3vpYRNWE0X-x!0@ZaAlrHnjcB{9%^n"
    b"v{dOH<VE8I{=#TDO>;_$#;@#HMP+8}lw~(?=gV|5pH<qJ?Y1*$)W?Qeq`BEzq8d!CT*`Ra^q~`z>lZ(QgoYE6!pEIGwTLM27{j3#"
    b"=MVQv6BTA?u#uk8S>4ucLz?OBu+`}`hiPValF&<Byy%3yE6<C^lO?&6&`T<}3&in~N7^^Y9B*lM1L4y7<aGN3JmxD78x5NS#<~Nv"
    b"$>fT4+}syUySYuD4Qb9+Vf!Tw2Eeg^Rz9DaTUcL$(nf+KX<AEaH-BiDhjll&g`l@dO&=EKn>P*aB8*$Zcg~oEOJQVM@qBvt7Q!#A"
    b"6}W)*WBA5}#A~;8vKoI8H7mkDy|`fi{<B^tVp+<|>QXc*TV)w)AeXKXU8*ys6bQ^$`gHOFlA{zBrHQ(iC7sm}jV9VaY0gExLJGb0"
    b"vX~b&<Xh_aS6Wn~TY3kXEa$vVF@=5|Sw@W!FI#DDB%iW{g)FGXaFyAOH3wcyT*wXR0|dj6_HjYdc8b}HbOKpqC%zjm!(5(COC~WV"
    b"Db6Qe4F8^5^C(<d0nGWSZ;9D&buO(Fk`+AyQi<XB)Q=ajkJ;HFU3wc@VX>)oXwiuZf5(;|$M7f3-~Q_XA63>CQM!#;*h8DXW<z6a"
    b"Qj3k9V^8_Fq`w8}*J;A~bPl56ne5dcE!19cHsIJj$=TQJ@hRHAd178;3#GVO5Cya4ELYmh`_7-fTq}(TL-55WWxZZ2D@TS0WCZ9#"
    b"I-Ch)PM+ZKT(7K22=p>#$?cCOG^gsJ70pw~jvp;&ejH5L#~c+asww_f#m=R{Mnr;Ev|2EO(28P`3p9(FCMaK6X<{}@14bGXl6Iud"
    b"l^Rga78y9rhJa5yd4YlG3DI_HN7T%f<b+n1N`mCyBn|U#RvIsTF$tH^*JyqpQNhS74A>-OytC$3VhW_j@g1VvVVd7zbEoRn2^LZJ"
    b"A<P6fohuzF;1~g&oHiEE*NIXhca8ewPZ<M2JkF`4%yXgdH1n(&<nn2Oo)SN1l(O<PtB#Z(6a|x`)+D%vtmm$jB;1k_2jAtuYBIws"
    b"l*Eci{8XJTs>P=cRh^YG@*EXkMPMGhnBGD6?&je%Q+H;<vi~ao`&0b;@537HU0-5mTUhwJzG0`?hMg5RjO#)P>G|wBh{)U~7H}Ba"
    b"D04gZ|FeX9KBieR(`3|t(707Pcd}wBd8>(0D{}?q5mxkq=>deRTW|pF1fC=}0iT<E0E@09c+lt-`Yp18(1wHVV8|Yb=e0``Ov|D$"
    b"M71I47PxzwY23z`weN%U&Q2zvud?G+e6_@b2Cc%wnU#<x+P73jXIU9t{9GDCa~sElhOERboFA^T7ay5>a`%M%3=)|L0NB_^aJ#`O"
    b"m38DVnD%rHo{`epttLOKoDwOhA~~(y!SWzE?U-pAnNOO#V0L4h7C5rA5-B~V@KhAM=|-AR^tpR=9yFZ#?We4qY8?A$Y)DJ@tsbM<"
    b"Rf8PQLm1@+xI}J(NyVsUuPWM)?NcAyDr2wk1}J4%y%3z=Sll<iWL)`HUh2iSz!vCr1yF^4ob9X*Bl+?Q%z%<T!lH$I!3nHNffoop"
    b"FZitR)d9#10vm`39AzHpwe`*(Bp@)GNlPKqx~Syxj_^9$(3XALk+>_DSi6(>*}B9pb|dlnVg&mOMgk00*hY?4Htq^NLrI<*lVldV"
    b"#WEt!_6W9FY;QWX=dta7U%(!ko#L`T|0dh+vCoc=ft{eXX>za~zxm(2Ng85%U|k})N_xHN-Vl9T-G&0ExeEpjktMjsIRmOLaCk)x"
    b"MIfI9iA%sRW&0x8P=#QMdlx7hm+wirYOB`1;kzlMF0pBHq}?OQgfu8CuIx2>ji}|q6Q@s65u0l010B1%8wh`xEtLnFCffTEce6fx"
    b"q}_nS{l3_f@N#OezI+h6%A*D!N=xTY)h}JoVgA4oE4(T6L8G-6Ww{@qtp-R&R?g=s1S~B=Z<2Ls$~XodouD*P2GZnW*+fLAD*|;2"
    b";&8HID?v2%7e4#}U)@s=Yi8l9sSLVCkmHK3siqnV0zA0003wTA=mZ#a5XR(%F6r>hTM?Tu7pnqqCqZ=U;$k?6mTX|dAo3wB!@h>#"
    b"jj!;t%>_a&Y9Y!+9DMU8D;ES8!D~{IHTk9#$c0Fe(MuW0Fd@1{pPUtc0+`7}zM}YML7KT}oX5LN1Bg*c)gYDsK)h870XCV4mS7R!"
    b"hzb~~Kf^);Ml5l?^dQp=lz!;D%Oq=eAKZ9B2<~}T8>_@$$i^(?mv1l<(;&?QMhxK8zkwJyzzYvGQUZ<t7`(D+YF8UmcH@b4oXz&}"
    b"Nruowl=C&j3?f)$pUIOf&mD}t<g0b6u2{&Ev$ZGZYfmoLp1e3%V*}n(=urrZnb^Cgp^bDT?Q4KA4XcBtv=3WAN6Q5+hb;ab!pNd="
    b"MI^csqOzcnkcH}5-{8}Eti&s&(2f%^^>K*=v6L{(VK~2ETYqspVKCGL=O|l^!N24OWO`;dVPGVB{o%(Jo}seo(nmWCG_)`iP{nKq"
    b"u@bc@p6x{t!5Y!NgQmk|#emObzJ#bUn`{)pFF~X%QOQrhBM~eG5@gMT>3otL@gUD583THBzj$Q>zeY$3tjy%se<MsKYcBzJFj+*5"
    b"8*<`z7db41AXb-tm1QgZEcCqy8EwYifbSN|R3~rc^#BXT+09naS$T^ua<35x1DdX>!qZL(8@&i204cT+5jI4B_-iQfZs2$KZV57U"
    b">6rj8lrvJ*Q6e0Y<0>D*h|OodfNKw6jIB!mpupl2uKBPRB21UM@j$*yqVb|-7zz~zEDl}dKV7isPZ_I>h09n?I~OH<u-0nc5QR+E"
    b"ZYfu=d*jW5kjPgCLfYPK?E6_VzQ3ae(G;dNELI^(8qor6f+=n(Vbr31M|8R!v7;78viPHG=<Jk*L0e>8tn^Na(M1L3V;?;HABp8<"
    b"QM$jXUK_w{oFll*m$o9dg%6(Q0=}B~$Wsq1g@lw6n!CAC{MiS@%vre;u@jOj7=%a$GR5WVBn}pexM_&%Y?%tvN@<2NQslj?tL*?>"
    b"JhR1|Y_Ah!q9d8M#b#|G69#;7^N0`+V<h$>hJeb#*i>~zI60}2;Dv;vpW1xbh;-~s7Yk!oGZP>ao9l!8CMoq=NBPaeqPy<5$1yJM"
    b"f_Rn?;1OQd;8{2ai9(8f8dAQDlI3DCj}f0Ra@bwaQheq;ZIpVGuX~Id!D#-*JeqW*5Tx8pg?=S$xs!+JklMKk96{j_<qkoM$5>l*"
    b"k!#_WI~c2$PmV8;5vT$ovo?4`RPzpk#Z$JZlfT!6CD)oZ9-#{+ehCtxe`>$0ut>%(L8*WTo4|wVJUhQcSVtxqtftXdG#xNNg3yu{"
    b"c)CFP2ZB-DzOy|ZA!I3188fEf13a>|C<y4rx4i2FN5~=(O%@!LAfHgBPlmh-n$-}}VDG`07SM!2UciFPZw8&v69}yE5piJsKMqwk"
    b"3|1TL-5_M^L7OebP#hT$=kF3LVN{=mh;7NJJi?4KDm6<vQY_pyOQ9Fi9@z8ibLZDwP~nFBnulgNzt%!0<yZbH96^nyWV;yFTJdU;"
    b"&TnIHafkAPBdL^5(>dW*<`To>s;qB&iv95@c2m68qgdtcTJF9qqghcI^c($6=ta@;tkC<2OnyR%ETpF5kd6iCID?3o2}sKfj}{4e"
    b"+H>r4<=BEVY5%i!Fl$qbwg9Q+tXmJPly*Id)EK&~BKBwvt$e)&jEq}1x0a|0512FW_ukI^fk=2afM%3TK%`}4iEc=B-G5t;jp^}`"
    b"Qj3>3xWMLByjvm=-x`R;8k-0fNXDbvFEyR7rr3B}N7tU33z4inhOr?X=V4lxigiep-UVsSa>!Cwg0Oi5Kr~&y@vZzx;5X!U-E;3V"
    b"LM-E30v|2kst16@1=)olCXveaH94VdC#z_pCtQzOut1~aZHr~$u?WFN{yjJslnn>=>(kyi*z;)xI@R;*8<J@bgJn!w2ZTjj%7BQg"
    b"FBx!T`79#*X+y7BsuYeFF6HM*mK(v5F(vD8Evmd4T;jphEkQb1CU>~~&&iO>oZ}RiSSnBvx2ckN;F%zoMmX(p`-E_-jU1>3ZEJ#u"
    b"aYBCzf)UGn0!?a;f;1*R3F@?1?4aD5{m;@Pt^)BHK{z>|hbMn5Z!+;0srTd&y;1zYL*VR5VUwh-;r#YTM>NL<X*LZPl#pUA7Gc23"
    b"Q3Y|qbeXe2WzS0MRi>-3yp&k2WJ8QQ2U6&{l|bH#X0V!RI^bY$rEUsFP0pST%~S<wRYqzx*7D&5^wgw^JRUnxD{7z`BR_~ys$`OR"
    b"PIR~}0)@|1^jfFoJH2-IYDBI<WFD!~wR~+h40u*23!G3gc7VmQQy~(TL?^3g=96PawiMiRV;-5gtX&&&;yUVfM~r++DjQ0bfgf4V"
    b"*9P5BLz2|x_ni1~Qxw+nZNl-d5uE)cDbIFGiW8Z{&ARr}d*6?&^nT8RsihJ}D>0$b({L6p+0){40pwbmzD<qA0_>ThMi5toae1)5"
    b"&g~!xASQcme74-UITUNLBReDQj>h1~#AFKF0&}puhAStiKa(AYwGy7TQN%W_Q6rM#JidifeSg)8*=I!?2c~Fx)5v5Ud{)?8%hFjF"
    b"o8r85RU`<_3RkYVMYM)UDN4)J>ThMU+RA*wJUz-Wd5i9OTe6wf9b9vgEWu+5GMjE17*ZF$8}Fw#sK`+?=#$Hc?kCw*F9&Ivim#7S"
    b"spwUp@&n7+@MnfEo?UCo)xYq)(}WXf9IPR^3cC-AT&e{ABbfr4VOYc5GXroo^JpoIaiZFU=xl}P_z`^UlsfP_ewLZ|+`-l8eKF=`"
    b"<~aQxD0T^9%ikm>Lol29(*U<b72-vcft^8tJtO5Nny0;Kw1A#AZA?gUJ}*CMVZznAMupPp8mQH7g_eLevj-~OQFQx~gio_$(pf}P"
    b"86H|RWy+xn-9w7%l%@hf@$Pp(e~2B>EudU~(^G+Q$);xskbj3=CA{vBWkXTHO0h_yp(BQGn!|%26|>jWJ7m2N*!yt^R*SxJleYwb"
    b"+{)zuT(bfw40Y$L_n~`x?Z3J9R}#Wu>R?R{6_)$50J50%Bmt17aD)ZWirJ0?UID2IT)zlAw1Iyw@F|vI%Sb&^0w<nS=R>+`2FJW>"
    b"w#?0C%ZzztIL4kggks)CF2d*Ltj#8yu14=Qp3o!mEyk)o*^dsW87q}QVUa3<dIFnl_nt!(9Sl>xi@*!70_KL0+FPT~370%1Pm^5*"
    b"w+^mGwNm|v3tF|7DBB=l=72~(AwE<rPnM2~<`S^TMXt^8=l*Q;uFmu4)4Fe);D<r5W`Z9*3bhe=5`Qe?4?V$O|K#1)2c4gr(J3VL"
    b"EE7y@3`k~m%3kY?&fl+EaQPlw$l$oWKHO8WJxF`=6pt|`77kc~0eKKtPfy{?6%ivxnp9TxGzmRF0XNhm9Nga)&v0o<F!7tBQmpIo"
    b"wEH>;{#U~1(g29HN}k{EuzSpU%6TWD#8YvNg@CDtZhi_>_8Lo%T5G|yhiS7g<#_pr$k<NoGV$CUK+-6<e*^D663^g|&f882u(h|G"
    b"JP6qk>;jcLpYZDS2S9rSX;4FiHipIA#d99Xa;Sv494aoYLu&@_V8-j{_K?xE2MaC?m=Wxaepezn{M81y#H%M~+xlyZh^E|HL>`aq"
    b"8Q2K?6l!3ej)$<8H-mI`Mt~(SCmF!?8Lwn!OnP%pb##sB?*aq8CKaJIEW5qM;6&GJ7_AtKM=`-Z4;8D;=%O7SPCFRI)C9I04WyCK"
    b"W{JvvqU@I{KsJVJt<_#RURlCHmdsTFt2~Q($To8ccjHb3jeDxOPrJ1RQU~adwAvGWdS1~o+d!4?>8mNcOOp(jr39#j$pOd#Z%zOU"
    b"84LyJI!KDUA%s7Sc_G;4A^AiBb+^S#W(9nlQ~y67fl@iwp-u&!`rU+D5Y@!L2y`-7@?(L~RLu&|5N+<a3mylW^`lolIG?kZenSM|"
    b"n{G!JMEKQTmGh=@0D+sI?0zqs#>zqo**Ndowk96i!X>M?n9TrTE@=Drj9CfG5B@3>?z-D-!0WKol4TVnH9X1DxrWC*O+HJS+y;*i"
    b"p~*56a}$=7=H)sPK{g_wMQ(mk#r~vdb8lxpQP!-oG`A#AgzDbD+!JRtarRmt9am;dFEuVjqVt;M$yGSsQK;ng&v-ajg#R|#t-{i5"
    b"Qrh0Yd}5i-cg2%AQ0mv=wE&snNVW(UU{pR-`H=|67(JFjcu$bVfw(n0mbxuBBuCY<RJf5UZLlY&OXb+5&vKf=y`hgwk9$M%$+2Ul"
    b"v-062DN)H$xaZ0}SLV3#(&;+yYPcxnB{>^=DoLt*JM!Xqe$P_mvZ6L%#mq$v<a>W_NIoVe4PB3;;8DwsHL<8!Wh>V`sb-|%we_Y@"
    b"-jk$RKyJm5WtQX?1Sw5PL5^^8{`(?`SBLbVy*TgZ-9v&Z6}t7@mCY0A-qd_D{8?pU?u<s6p}A+!J%bi9X#O(YQbSYRrMsz_DYj<l"
    b"j<~pJm&Oy--q;cKZ+^yeZ)ZNc`*HKo)RJW_SQaeD1q>g>Ww{Zm_k`I5Hn*qEGV60=)|9rVK<ITqgMY#Dlsl16j5qh@<&&h%DpT{p"
    b"?8!{bJ#p@dv&Mx<G6~M8-@U4KZr)-DPvm6|e64Y&Oz5lZ@9^XxmP`&J?*xlI7PY~%>C}u}m(AH5p-(Hh$WV;(hJ30FX^qrP0<~H~"
    b"EkSGnjTWJ_F)FQx<~@ftgUR|V+8PX;R=51*WC;xAZF7r-4>`fWnTct`5+73SL&w9Fbra8L@_alyG08GID@Wru${<E*8PApZVYtZw"
    b"O4`brxxyMeK*`!Q@sj72b)-eweaSL<Z<hl{Ah7H(WGMvc5lF9CcQas$tmEk&-0}tDf`yTVg~lLZ3liGRAW?J(S9xLvZH`OaFj|H+"
    b"Zl$k;RY{VDH83A;dEobP(&aouJ-;1lYv}l27^)9gCm~G8B>)njKHyB~l9Tl+*m<rS_a4Sb`9WEyxH5^uZ!)zB2gTo_3y^%_I+%hL"
    b">ds-n<NF}N58!HCU%W!@tPNd)bl;U}OI+k@TDtzsKl=(j@-Az34%mn-H<wRB1vZ}Yhlkgp?<%+ZWZs||)Lgkemibwxpm2G{fb7I!"
    b"87W+tS20L@DyB|us6r?`bnoZ!*BgKt#a6+1sUvj{{dM`&gdc9aF!8gKB_|H1UKJVQ@|q>?SWh29S#b!Xn|;<EcRsaprSNh3*za}V"
    b"m?WeoQGadsKMuMM_>(eU{L>-hsgcM!+T6sSVS1*CA{gOX${_1t8KJ!ez>D1=A`?Ub7sVCUe&h^?F4)4559q2h{(Kb8Z9y+mFLY5T"
    b"ir^)|uBD5c`EUbIbjy^fvfq!B+n@denB9_eVdbcr>moW5{5k-d>1Fc<0A3(h5Nm<RhypiIa-bH}xlKp0;1rKb(+aVdh;_nhXj7qz"
    b"TVcLyp=Gi)Bf>g(>tU;_t(;xaWiNtoo@aTbDX^anG7nN326U7LGye#eA>^hG@~x7ktH26HWINhMK(B6s&{x!YVIwG~$t?D=#$-t^"
    b"T7=6+K$~Rp-ensyx*FlISB!=Y1Z%^c_x3U=9vS$}g5RK`2!@44)hEjYswGCqVh++;>GG>RuyVc*WL{oG9dJ760EtEJtSHWvrLCUm"
    b"EL&c+0VABo0p1c&*pRHQ6Up3E3x(<qcTFoIqvYB)?hLn?Bsl$JScd?q0f*5X@hMbFu6fE{Fz*aMc3>`aQR#i^f7qrrSxY*fT_-@0"
    b"KA|48X+WP%if(dXZ2Ul;qqjBugJ#78pFl0X6D00VVa5_{s>EW;T&2WbqiiZ{M$XhyPXOV=qRI78KYGzu80(C7B!(bWu`cuR|0e7^"
    b"LN0iF*qwbB+}`DFQ=&_3nInQ%&aFeKWfE1CQi~|+xRB<{G^7x}MnSBVo!8Oj<>lL_5_4YvJM{|Aa{HIELL}!Y4~x?EsT7fUMyICo"
    b"s9-9swNP;Wmq%}k%KD|EGT)S}7WiVM4u$8xl%s3Q;yG1+kq-;W^^5wEpusPHW;iOV8+7xWWK<LC;~<}|?_jO-#j|%krJq)MZt>hL"
    b"ST_|EvGz{UP^^8Id<_<8S;zA*yhaylEqhv;_rLu8%l`u?liZE"
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
